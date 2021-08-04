import json
from zero_sdk.network import Network
from zero_sdk.utils import generate_mnemonic, get_home_path, hash_string
from zero_sdk.wallet import Wallet
from zero_sdk.allocation import Allocation
from zero_sdk.config import default_network_config_obj, default_wallet_config_obj
from zero_sdk.utils import pprint

# txn_hash = "17297e21e21c59b32de70f082a8668166cc9cb06eb5071abd2907089c45c7238"


# import hashlib
import hashlib

network = Network.from_object(default_network_config_obj)
wallet = Wallet.from_object(default_wallet_config_obj, network)

res = wallet.create_read_pool()
print(res)
