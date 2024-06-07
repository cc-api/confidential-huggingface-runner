"""A Keybroker module.

This module provides an object-oriented design for key broker client to connect with
key broker server (KBS), get model decryption key from the KBS.

Classes:
    KeyBrokerClientBase: An abstract base class for key broker client.
    SimpleKeyBrokerClient: A concrete class implementing the KeyBrokerClientBase to connect
      a simple KBS.
"""

from abc import ABC, abstractmethod
import base64
import logging
import requests

from cctrusted_vm import CCTrustedVmSdk
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric import padding
from .crypto import AesCrypto

LOG = logging.getLogger(__name__)

# Set the connection timeout to 10s
TIMEOUT = 10
# Set the connection retry times to 3
RETRY_TIMES = 3
# Set http connection succesfull code
HTTP_OK = [200]
# Set RSA key configuration
RSA_PUBLIC_EXPONENT = 65537
RSA_KEY_SIZE = 3072


class KeyBrokerClientBase(ABC):
    """An abstract base class for key broker client.

    This class serves as a blueprint for subclasses that need to implement
    `get_key` methods for different types of KBS.
    """

    @abstractmethod
    def get_key(self, server_url: str, key_id: str):
        """Get a key from KBS.

        This method is used to get a key from KBS.

        Args:
            server_url (str): The url of KBS.
            key_id (str): The id of the key.

        Raises:
            ValueError: If the server_url or key_id is None.
            RuntimeError: If get quote or get key failed.
            NotImplementedError: If the subclasses don't implement the method.
        """
        raise NotImplementedError("Subclasses should implement get_key() method.")


class ItaKeyBrokerClient(KeyBrokerClientBase):
    """A implementation for key broker client.

    This class implement `get_key` in `KeyBrokerClientBase` abstract base class to connect
    to a ITA KBS: https://github.com/intel/trustauthority-kbs
    Here is an example flow of a ITA KBS:
        - Accept a quote and a public key from client.
        - Verify the quote and do attestation, return if verify failed.
        - Get the user key from key management server (KMS), generate a symmetric wrapping
          key (SWK) to encrypt the user key (wrapped_key).
        - Encrypt the SWK by the public key from client (wrapped_swk).
    For a key broker client, here is an example flow to get a key from KBS:
        - Get and replay all event logs, and verify by the measurement register.
        - Generate 2048 bit RSA key pair (a public key and a private key).
        - Encode the public key to base64 for transferring (user_data).
        - Get quote in the TEE with the hash of the public key for measurement (quote).
        - Request wrapped_key and wrapped_swk from KBS with quote and user_data.
        - Decrypt the user key by the SWK.
    """

    def get_key(
        self, server_url: str, key_id: str
    ) -> bytes:  # pylint: disable=too-many-locals
        """Get model key by key ID from the KBS.

        This method get and replay all event logs, and verify by the measurement register, then
        construct the request headers and body to request the wrapped_key and wrapped_swk from KBS,
        decrypt the user key by SWK and return the key.

        A example requests and response:
            - request headers:
                Accept:application/json
                Content-Type:application/json
                Attestation-Type:TDX
            - request body:
                {
                    "quote":"",
                    "user_data":""
                }
            - response body:
                {
                    "wrapped_key":"",
                    "wrapped_swk":""
                }

        Args:
            server_url (str): The url of KBS.
            key_id (str): The id of the key.

        Returns:
            bytes: The bytes of the key.

        Raises:
            ValueError: If the server_url or key_id is None.
            RuntimeError: If get or verify event log failed, and if get quote or get key failed.
            NotImplementedError: If the subclasses don't implement the method.
        """
        if server_url is None:
            raise ValueError("KBS server url can not be None")
        if key_id is None:
            raise ValueError("KBS key id can not be None")

        private_key = rsa.generate_private_key(
            public_exponent=RSA_PUBLIC_EXPONENT, key_size=RSA_KEY_SIZE
        )
        pubkey = private_key.public_key()
        pubkey_der = pubkey.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        LOG.debug("Getting TDX Quote by CCNP")
        user_data = base64.b64encode(pubkey_der).decode('utf-8')
        quote = CCTrustedVmSdk.inst().get_cc_report(data=user_data)
        if quote is None:
            raise RuntimeError("Get TDX Quote failed")
        quote = base64.b64encode(quote.data).decode('utf-8')

        req_body = {"quote": quote, "user_data": user_data}

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Attestation-Type": "TDX",
        }

        LOG.debug("Getting key from the KBS")
        resp = None
        for _ in range(RETRY_TIMES):
            try:
                resp = requests.post(
                    server_url,
                    json=req_body,
                    headers=headers,
                    verify=False,
                    timeout=TIMEOUT,
                )
                if resp.status_code in HTTP_OK:
                    break
            except requests.exceptions.ConnectionError:
                LOG.debug("Connect error from the KBS, try again")

        if resp is None or resp.status_code not in HTTP_OK:
            raise RuntimeError("Unexpected response from the KBS")

        resp_body = resp.json()
        if "wrapped_key" not in resp_body or "wrapped_swk" not in resp_body:
            raise RuntimeError("Empty key response from the KBS")

        wrapped_key = base64.b64decode(resp_body['wrapped_key'])
        wrapped_swk = base64.b64decode(resp_body['wrapped_swk'])

        LOG.debug("Decrypting the SWK")
        swk = private_key.decrypt(
            wrapped_swk,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        crypt = AesCrypto()
        return crypt.decrypt(swk, wrapped_key)
