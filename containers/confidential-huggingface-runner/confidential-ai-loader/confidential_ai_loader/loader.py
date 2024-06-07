import json
import logging
import os
import shutil
import subprocess
import sys
from multiprocessing import Pool

from abc import ABC, abstractmethod
from huggingface_hub import try_to_load_from_cache
from .crypto import AesCrypto
from .keybroker import ItaKeyBrokerClient

LOG = logging.getLogger(__name__)

ENCRYPTION_CONFIG = "encryption-config.json"


class LoaderBase(ABC):
    """An abstract base class for loader.
    This class serves as a blueprint for subclasses that need to implement
    `prepare_model` method for different types of loader.
    """

    @abstractmethod
    def prepare_model(self, model_input, model_output):
        """
        Prepare model for AI models.
        """
        raise NotImplementedError("Subclasses should implement prepare_model() method.")


class HuggingFaceLoader(LoaderBase):
    """Hugging Face Loader to prepare (decrypt) AI models"""

    def decrypt_file(self, secret, in_path, out_path):
        '''
        Decrypt using the specified secret the existing file specified by
        in_path and write the result to out_path
        (whose dirname is assumed to already exist).
        '''

        LOG.info(f'\tDecrypting {in_path} to {out_path}')

        crypt = crypto.AesCrypto()

        crypt.decrypt_file(secret, in_path, out_path)

    def decrypt_files(self, secret, files, out_dir):
        '''
        Decrypt the specified set of paths using the specified secret (key)
        and write the unencrypted files to directory `out_dir'.

        For performance, the decryption uses multiple processes, one per file.

        Notes:

        - All files in the specified list are assumed to live in the same directory.
        - The output directory is assumed to exist and be empty: no check is
          performed to ensure an existing file is not overwritten.
        - The output files will have the '.aes' extension removed when created
          in the output directory.
        '''

        cpu_count = os.cpu_count()

        files_count = len(files)

        # Always leave 1 cpu free.
        max_cpus = cpu_count - 1 if cpu_count > 1 else 1

        cpus = files_count if max_cpus >= files_count else max_cpus

        # Repeat the secret 'n' times
        secrets = [secret] * files_count

        def rename_file(file):
            name = os.path.basename(file)
            name = name.removesuffix('.aes')
            return os.path.join(out_dir, name)

        out_files = map(rename_file, files)

        out_files = list(out_files)

        args = list(zip(secrets, files, out_files))

        with Pool(cpus) as p:
            results = [p.starmap_async(self.decrypt_file, args)]

            # This step is essential to ensure the async futures are waited for.
            for result in results:
                _ = result.get()

    def prepare_model(self, model_input, model_output):
        """Prepare AI models in Hugging Face.

        This method is design to get the encrypted models in the cache directory of
        Hugging Face model project, a `ENCRYPTION_CONFIG` is a configuration file including
        the KBS information and key id, call keybroker to get the key and decrypt the models

        """
        config_path = try_to_load_from_cache(model_input, ENCRYPTION_CONFIG)
        if isinstance(config_path, str):
            LOG.info("Models are encrypted, try to decrypt models first...")
            model_name, snapshots, commit_id = config_path.split('/')[-4:-1]
            origin_refs = config_path.split('snapshots')[0] + 'refs'
            shutil.copytree(origin_refs, os.path.join(model_output, model_name, "refs"))
            with open(config_path, 'r') as f:
                model_dir = os.path.dirname(config_path)
                new_model_dir = os.path.join(
                    model_output, model_name, snapshots, commit_id
                )
                if not os.path.exists(new_model_dir):
                    os.makedirs(new_model_dir)
                encryption_config = json.load(f)
                if encryption_config['kbs'] == "ITA_KBS":
                    kbc = ItaKeyBrokerClient()
                    kbs_url = encryption_config['kbs_url']
                    key_id = encryption_config['key_id']
                    LOG.info("Try to get the key from the KBS...")
                    key = kbc.get_key(kbs_url, key_id)

                    LOG.info("Try to decrypt files: ...")
                    files = encryption_config['files']

                    paths = map(lambda file: os.path.join(model_dir, file), files)
                    paths = list(paths)

                    self.decrypt_files(key, paths, new_model_dir)
        else:
            LOG.warn("Models are not encrypted...")

    @staticmethod
    def hf_cli():
        """
        CLI tool
        """
        logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)

        env = os.environ.copy()
        try:
            model_id = env['MODEL_ID']
            model_hub = env['MODEL_HUB']
        except KeyError:
            LOG.error("MODEL_ID / MODEL_HUB environment variables not set")
            exit(1)

        env["HF_HUB_OFFLINE"] = "1"
        env["HF_HUB_CACHE"] = model_hub
        # Set L2 size to 128M
        env["OPENBLAS_L2_SIZE"] = "134217728"

        hf_loader = HuggingFaceLoader()
        hf_loader.prepare_model(model_id, model_hub)

        subprocess.run(sys.argv[1:], env=env)
