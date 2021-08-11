from datetime import timedelta
from time import sleep
import os
from pathlib import Path
from time import time
import json

from zero_sdk.const import (
    INTEREST_POOL_SMART_CONTRACT_ADDRESS,
    STORAGE_SMART_CONTRACT_ADDRESS,
    FAUCET_SMART_CONTRACT_ADDRESS,
    MINER_SMART_CONTRACT_ADDRESS,
    Endpoints,
    AllocationConfig,
    TransactionType,
    TransactionName,
)
from zero_sdk.network import Network
from zero_sdk.utils import hash_string, generate_random_letters, create_allocation
from zero_sdk.bls import sign_payload
from zero_sdk.connection_base import ConnectionBase


class Wallet(ConnectionBase):
    def __init__(
        self,
        client_id,
        client_key,
        public_key,
        private_key,
        mnemonics,
        date_created,
        network,
        version="1.0",
    ):
        self.client_id = client_id
        self.client_key = client_key
        self.public_key = public_key
        self.private_key = private_key
        self.mnemonics = mnemonics
        self.version = version
        self.date_created = date_created
        self.network = network

    def _init_wallet(self):
        # Implement wallet init
        pass

    def _validate_wallet(method):
        """Initialize wallet
        Check the wallet is initialized before every API request
        If wallet is not initialized, create a new wallet.
        """

        def wrapper(self, *args, **kwargs):
            print(self)

            if self.client_id is not None:
                return method(self, *args, **kwargs)
            else:
                self._init_wallet()
                raise Exception(
                    "Wallet is not initialized, call 'create_wallet, init_wallet or recover_wallet' methods to configure wallet"
                )

        return wrapper

    def _execute_smart_contract(
        self,
        payload,
        to_client_id=None,
        transaction_value=0,
    ):
        if not to_client_id:
            to_client_id = STORAGE_SMART_CONTRACT_ADDRESS
        return self._submit_transaction(
            to_client_id,
            transaction_value,
            payload,
            transaction_type=TransactionType.SMART_CONTRACT,
        )

    def _execute_faucet_smart_contract(
        self, method_name="pour", input="pour_tokens", transaction_value=10000000000
    ):
        payload = json.dumps({"name": method_name, "input": input})

        return self._execute_smart_contract(
            to_client_id=FAUCET_SMART_CONTRACT_ADDRESS,
            transaction_value=transaction_value,
            payload=payload,
        )

    def _submit_transaction(self, to_client_id, value, payload, transaction_type):
        hash_payload = hash_string(payload)
        ts = int(time())

        hashdata = f"{ts}:{self.client_id}:{to_client_id}:{value}:{hash_payload}"

        hash = hash_string(hashdata)
        signature = self.sign(hash)

        data = json.dumps(
            {
                "client_id": self.client_id,
                "public_key": self.public_key,
                "transaction_value": value,
                "transaction_data": payload,
                "transaction_type": transaction_type,
                "creation_date": ts,
                "to_client_id": to_client_id,
                "hash": hash,
                "transaction_fee": 0,
                "signature": signature,
                "version": "1.0",
            }
        )
        headers = {"Content-Type": "application/json", "Connection": "keep-alive"}
        res = self._consensus_from_workers(
            "miners",
            endpoint=Endpoints.PUT_TRANSACTION,
            method="POST",
            data=data,
            headers=headers,
        )
        return res

    def lock_tokens(self, amount_tokens, hours, minutes):
        if hours < 0 or minutes < 0:
            raise Exception("Invalid time")

        duration = f"{hours}h{minutes}m"
        num_tokens = amount_tokens * 10000000000

        payload = json.dumps(
            {
                "name": TransactionName.LOCK_TOKEN,
                "input": {"duration": duration},
            }
        )

        res = self._execute_smart_contract(
            to_client_id=INTEREST_POOL_SMART_CONTRACT_ADDRESS,
            payload=payload,
            transaction_value=num_tokens,
        )
        return res

    def get_balance(self, format="default") -> int:
        """Get Wallet balance
        Return float value of tokens
        """
        endpoint = f"{Endpoints.GET_BALANCE}?client_id={self.client_id}"
        empty_return_value = {"balance": 0}
        res = self._consensus_from_workers(
            "sharders", endpoint, empty_return_value=empty_return_value
        )
        try:
            bal = res.get("balance")
            if format == "default":
                return bal
            elif format == "human":
                return "%.10f" % (bal / 10000000000)
            else:
                return bal

        except AttributeError:
            return res

    def get_user_pools(self):
        endpoint = f"{Endpoints.GET_USER_POOLS}?client_id={self.client_id}"
        empty_return_value = {"pools": {}}
        res = self._consensus_from_workers(
            "sharders", endpoint, empty_return_value=empty_return_value
        )
        return res

    def add_tokens(self):
        return self._execute_faucet_smart_contract()

    def get_read_pool_info(self, allocation_id=None):
        url = f"{Endpoints.SC_REST_READPOOL_STATS}?client_id={self.client_id}"
        res = self._consensus_from_workers("sharders", url)

        if allocation_id:
            return self._filter_by_allocation(res, allocation_id)
        return res

    def get_write_pool_info(self, allocation_id=None):
        url = f"{Endpoints.SC_REST_WRITEPOOL_STATS}?client_id={self.client_id}"
        res = self._consensus_from_workers("sharders", url)

        if allocation_id:
            return self._filter_by_allocation(res, allocation_id)

        return res

    def create_allocation(
        self,
        data_shards=AllocationConfig.DATA_SHARDS,
        parity_shards=AllocationConfig.PARITY_SHARDS,
        size=AllocationConfig.SIZE,
        lock_tokens=AllocationConfig.TOKEN_LOCK,
        preferred_blobbers=AllocationConfig.PREFERRED_BLOBBERS,
        write_price=AllocationConfig.WRITE_PRICE,
        read_price=AllocationConfig.READ_PRICE,
        max_challenge_completion_time=AllocationConfig.MAX_CHALLENGE_COMPLETION_TIME,
        expiration_date=time(),
    ):
        future = int(expiration_date + timedelta(days=30).total_seconds())

        payload = json.dumps(
            {
                "name": "new_allocation_request",
                "input": {
                    "data_shards": data_shards,
                    "parity_shards": parity_shards,
                    "owner_id": self.client_id,
                    "owner_public_key": self.public_key,
                    "size": size,
                    "expiration_date": future,
                    "read_price_range": read_price,
                    "write_price_range": write_price,
                    "max_challenge_completion_time": max_challenge_completion_time,
                    "preferred_blobbers": preferred_blobbers,
                },
            }
        )

        res = self._execute_smart_contract(payload, transaction_value=lock_tokens)
        transaction_hash = res["entity"]["hash"]
        sleep(5)
        confirmation = self.network.check_transaction_status(transaction_hash)
        hash = confirmation.get("hash")
        if hash:
            return create_allocation(hash, self)

        return {
            "status": "unconfirmed",
            "message": "Allocation creation could not be confirmed",
        }

    def _filter_by_allocation(self, res, allocation_id):
        pool_info = []

        if allocation_id and res["pools"]:
            pools = res["pools"]
            for pool in pools:
                if pool["allocation_id"] == allocation_id:
                    pool_info.append(pool)

            if len(pool_info) == 0:
                return []
            else:
                return pool_info

    def list_allocations(self):
        url = f"{Endpoints.SC_REST_ALLOCATIONS}?client={self.client_id}"
        res = self._consensus_from_workers("sharders", url)
        return res

    def sign(self, payload):
        return sign_payload(self.private_key, payload)

    def save(self, wallet_name=None):
        if not wallet_name:
            wallet_name = generate_random_letters()

        data = {
            "client_id": self.client_id,
            "client_key": self.public_key,
            "keys": [{"public_key": self.public_key, "private_key": self.private_key}],
            "mnemonics": self.mnemonics,
            "version": self.version,
            "date_created": self.date_created,
        }

        with open(
            os.path.join(Path.home(), f".zcn/test_wallets/wallet_{wallet_name}.json"),
            "w",
        ) as f:
            f.write(json.dumps(data, indent=4))

    @staticmethod
    def from_object(config: dict, network: Network):
        """Returns fully configured instance of wallet
        :param config: Wallet config object from json.loads function
        :param network: Instance of configured network
        """
        return Wallet(
            config.get("client_id"),
            config.get("client_key"),
            config.get("keys")[0]["public_key"],
            config.get("keys")[0]["private_key"],
            config.get("mnemonics"),
            config.get("date_created"),
            network,
            config.get("version"),
        )

    def __repr__(self):
        return f"Wallet(config, network)"

    def __str__(self):
        return f"client_id: {self.client_id} \nnetwork_url: {self.network.hostname}"

    # -----------------
    # TODO: Fix methods
    # All below methods need confirmation
    # -----------------

    def miner_unlock_token(self, pool_id, id, type):
        """Unlock tokens from miner"""
        payload = json.dumps(
            {
                "name": "deleteFromDelegatePool",
                "input": {"pool_id": pool_id, "id": id, "type": type},
            }
        )
        res = self._execute_smart_contract(
            to_client_id=MINER_SMART_CONTRACT_ADDRESS,
            payload=payload,
        )
        return res

    def miner_lock_token(self, transaction_value, id, type):
        """Lock tokens on miner"""
        payload = json.dumps(
            {"name": "addToDelegatePool", "input": {"id": id, "type": type}}
        )
        res = self._execute_smart_contract(
            to_client_id=MINER_SMART_CONTRACT_ADDRESS,
            transaction_value=transaction_value,
            payload=payload,
        )
        return res

    def blobber_lock_token(self, transaction_value, blobber_id):
        """Lock tokens on blobber"""
        payload = json.dumps(
            {"name": "stake_pool_lock", "input": {"blobber_id": blobber_id}}
        )
        res = self._execute_smart_contract(
            to_client_id=STORAGE_SMART_CONTRACT_ADDRESS,
            transaction_value=transaction_value,
            payload=payload,
        )
        return res

    def blobber_unlock_token(self, pool_id, blobber_id):
        """Unlock tokens from pool id and blobber"""
        payload = json.dumps(
            {
                "name": "stake_pool_unlock",
                "input": {"pool_id": pool_id, "blobber_id": blobber_id},
            }
        )
        res = self._execute_smart_contract(
            to_client_id=STORAGE_SMART_CONTRACT_ADDRESS,
            payload=payload,
        )
        return res

    def get_locked_tokens(self):
        endpoint = f"{Endpoints.GET_LOCKED_TOKENS}?client_id={self.client_id}"
        empty_return_value = {
            "message": "Failed to get locked tokens.",
            "code": "resource_not_found",
            "error": "resource_not_found: can't find user node",
        }
        res = self._consensus_from_workers(
            "sharders", endpoint, empty_return_value=empty_return_value
        )
        return res

    def get_lock_config(self):
        endpoint = Endpoints.GET_LOCK_CONFIG
        res = self._consensus_from_workers("sharders", endpoint)
        return res

    def create_read_pool(self):
        payload = json.dumps({"name": "new_read_pool", "input": None})
        res = self._execute_smart_contract(payload)
        return res

    def allocation_min_lock(
        self,
        data_shards=AllocationConfig.DATA_SHARDS,
        parity_shards=AllocationConfig.PARITY_SHARDS,
        size=AllocationConfig.SIZE,
        preferred_blobbers=AllocationConfig.PREFERRED_BLOBBERS,
        write_price=AllocationConfig.WRITE_PRICE,
        read_price=AllocationConfig.READ_PRICE,
        max_challenge_completion_time=AllocationConfig.MAX_CHALLENGE_COMPLETION_TIME,
        expiration_date=time(),
    ):
        future = int(expiration_date + timedelta(days=30).total_seconds())

        payload = json.dumps(
            {
                "allocation_data": {
                    "data_shards": data_shards,
                    "parity_shards": parity_shards,
                    "owner_id": self.client_id,
                    "owner_public_key": self.public_key,
                    "size": size,
                    "expiration_date": future,
                    "read_price_range": read_price,
                    "write_price_range": write_price,
                    "max_challenge_completion_time": max_challenge_completion_time,
                    "preferred_blobbers": preferred_blobbers,
                },
            }
        )

        res = self._consensus_from_workers(
            "sharders", endpoint=Endpoints.SC_REST_ALLOCATION_MIN_LOCK, data=payload
        )
        return res

    def update_allocation(
        self,
        allocation_id,
        tokens=1,
        extend_expiration_hours=720,
        size=2147483652,
    ):
        future = int(time() + timedelta(hours=extend_expiration_hours).total_seconds())

        payload = json.dumps(
            {
                "name": "update_allocation_request",
                "input": {
                    "owner_id": self.client_id,
                    "id": allocation_id,
                    "size": size,
                    "expiration_date": future,
                },
            }
        )
        res = self._execute_smart_contract(payload, transaction_value=tokens)

        return res

    # --------------------
    # Versing pool methods
    # --------------------

    def get_vesting_pool_config(self):
        endpoint = Endpoints.VP_GET_CONFIG
        res = self._consensus_from_workers("sharders", endpoint)
        return res
