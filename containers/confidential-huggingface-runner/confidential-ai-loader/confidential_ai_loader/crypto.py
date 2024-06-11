from abc import ABC, abstractmethod
import argparse
import base64
import logging
import json
import os
import secrets
import struct
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

LOG = logging.getLogger(__name__)


class CryptoBase(ABC):
    """An abstract base class for crypto.
    This class serves as a blueprint for subclasses that need to implement
    `encrypt` and `decrypt` methods for different types of crypto.
    """

    @abstractmethod
    def encrypt(self, key, data):
        """Encrypt data by a key.

        This method is used to encrypt data by a key.

        Args:
            key (bytes): The key for encryption.
            data (bytes): The data for encryption.

        Raises:
            ValueError: If the key or data is None.
            NotImplementedError: If the subclasses don't implement the method.
        """
        raise NotImplementedError("Subclasses should implement encrypt() method.")

    @abstractmethod
    def decrypt(self, key, data):
        """Decrypt data by a key.

        This method is used to decrypt data by a key.

        Args:
            key (bytes): The key for decryption.
            data (bytes): The data for decryption.

        Raises:
            ValueError: If the key or data is None.
            NotImplementedError: If the subclasses don't implement the method.
        """
        raise NotImplementedError("Subclasses should implement decrypt() method.")


class AesCrypto(CryptoBase):
    """Advanced Encryption Standard (AES) crypto.

    AES ensures data confidentiality by transforming plaintext into ciphertext using a secret key,
    making it challenging for unauthorized parties to decipher the original data.

    Normally, the encrypted data format can be:
    -------------------------------------------------------------------
    | 12 bytes header | [12] bytes IV | encrypted data | [16] bytes tag |
    -------------------------------------------------------------------
    and the 12 bytes header:
    -----------------------------------------------------------
    | uint32 IV length | uint32 tag length | uint32 data length |
    -----------------------------------------------------------
    """

    def encrypt(self, key, data):
        """AES encryption.

        Args:
            data (bytes): The data for encryption.
            key (bytes): The key for encryption.

        Raises:
            ValueError: If the data or key is None.
        """
        if data is None:
            raise ValueError("The data can not be None")
        if key is None:
            raise ValueError("The key can not be None")

        aesgcm = AESGCM(key)
        IV = secrets.token_bytes(12)
        encrypted_data = aesgcm.encrypt(IV, data, None)
        header = struct.pack('<3I', len(IV), 16, len(encrypted_data))
        return header + IV + encrypted_data

    def decrypt(self, key, data):
        """AES encryption.

        Args:
            data (bytes): The data for encryption.
            key (bytes): The key for encryption.

        Raises:
            ValueError: If the data or key is None.
        """
        if data is None:
            raise ValueError("The data can not be None")
        if key is None:
            raise ValueError("The key can not be None")

        header_len = 12
        iv_len, tag_len, data_len = struct.unpack('<3I', data[:header_len])
        iv = data[header_len : (iv_len + header_len)]
        raw_data = data[(iv_len + header_len) : -tag_len]
        tag = data[-tag_len:]

        LOG.debug(
            "Decrypt data, IV len %d, tag len %d, data len %d",
            iv_len,
            tag_len,
            data_len,
        )
        decryptor = Cipher(algorithms.AES(key), modes.GCM(iv, tag)).decryptor()
        decrypted_data = decryptor.update(raw_data) + decryptor.finalize()
        return decrypted_data

    def encrypt_file(self, key, input, output):
        """Encrypt a file.
        Args:
            key (bytes): The key for encryption.
            input (str): The input file for encryption.
            output (str): The output file for encryption.

        Raises:
            ValueError: If the input or output is None or not a file.
        """
        if key is None:
            raise ValueError("The key can not be None")
        if input is None:
            raise ValueError("The input can not be None")
        if output is None:
            raise ValueError("The output can not be None")

        if not os.path.isfile(input):
            raise ValueError(f"The input is not a file: {input}")

        with open(input, 'rb') as infile:
            data = infile.read()
            LOG.info(f"Encrypting file {input}")
            encrypted_data = self.encrypt(key, data)
            with open(output, 'wb') as outfile:
                outfile.write(encrypted_data)

    def decrypt_file(self, key, input, output):
        """Decrypt a file.
        Args:
            key (bytes): The key for decryption.
            input (str): The input file for decryption.
            output (str): The output file for decryption.

        Raises:
            ValueError: If the input or output is None or not a file.
        """
        if key is None:
            raise ValueError("The key can not be None")
        if input is None:
            raise ValueError("The input can not be None")
        if output is None:
            raise ValueError("The output can not be None")

        if not os.path.isfile(input):
            raise ValueError(f"The input is not a file: {input}")

        with open(input, 'rb') as infile:
            data = infile.read()
            LOG.info(f"Decrypting file {input}")
            decrypted_data = self.decrypt(key, data)
            with open(output, 'wb') as outfile:
                outfile.write(decrypted_data)


def main():
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="The utility to show how to encrypt model"
    )
    parser.add_argument(
        '-i', '--input', help='set input file or directory', dest='input'
    )
    parser.add_argument(
        '-o', '--output', help='set output file or directory', dest='output'
    )
    parser.add_argument(
        '-k', '--key', help='set encryption key with base64 encoded', dest='key'
    )
    args = parser.parse_args()

    if args.input is None or args.output is None or args.key is None:
        parser.print_help()
        exit(1)

    try:
        key = base64.b64decode(args.key)
    except Exception as e:
        LOG.error("Decode the key failed, key should be base64 encoded.")
        exit(1)

    encryption_config = {"kbs": "", "kbs_url": "", "key_id": "", "files": []}

    crypto = AesCrypto()
    if os.path.isdir(args.input):
        if os.path.isdir(args.output):
            for item in os.listdir(args.input):
                input_file = os.path.join(args.input, item)
                if (
                    os.path.isfile(input_file)
                    and not item.startswith('.')
                    and not item.endswith('.md')
                ):
                    output_file = os.path.join(args.output, item + ".aes")
                    crypto.encrypt_file(key, input_file, output_file)
                    encryption_config["files"].append(output_file)
            with open(args.output + "/encryption-config.json", "w") as config_file:
                json.dump(encryption_config, config_file)
        else:
            LOG.error("Output is not matching input.")
    if os.path.isfile(args.input):
        crypto.encrypt_file(key, args.input, args.output)


if __name__ == "__main__":
    main()
