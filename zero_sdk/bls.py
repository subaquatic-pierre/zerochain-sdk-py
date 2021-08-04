import subprocess
import secrets
from zero_sdk.lib.bip39 import encode_bytes
from zero_sdk.utils import get_project_root, hash_string

root_dir = get_project_root()

PASSPHRASE = "0chain-client-split-key"


def sign_payload(private_key, hash_payload):
    file_path = f"{root_dir}/zero_sdk/lib/bn254_js/sign.js"

    command = subprocess.Popen(
        ["node", file_path, private_key, hash_payload],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    sig, err = command.communicate()
    if err == None:
        if len(sig.decode()) != 64:
            return False
        else:
            return sig.decode()
    else:
        return False


def genereate_keys():
    file_path = f"{root_dir}/zero_sdk/lib/bn254_js/generate_keys.js"
    byte_array = secrets.token_bytes(32)
    mnemonic = encode_bytes(bytearray(byte_array))

    command = subprocess.Popen(
        ["node", file_path, mnemonic],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    keys, err = command.communicate()
    if err == None:
        split = keys.decode().split(" ")
        public_key = split[0]
        private_key = split[1]
        return {
            "public_key": public_key,
            "private_key": private_key,
            "mnemonic": mnemonic,
            "client_id": hash_string(public_key),
        }
    else:
        return False
