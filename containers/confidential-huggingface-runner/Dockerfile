FROM python:3.10-slim as ipex_base

RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN pip install intel-extension-for-pytorch==2.2.0 oneccl_bind_pt --trusted-host ipex-1711374217.us-west-2.elb.amazonaws.com --extra-index-url https://ipex-1711374217.us-west-2.elb.amazonaws.com/release-whl/stable/cpu/us/

FROM ipex_base as model_cache

RUN pip install huggingface_hub ${pip_mirror}
RUN huggingface-cli download --resume-download --repo-type model lmsys/vicuna-7b-v1.3

FROM model_cache

ARG huggingface_space=""
RUN curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.deb.sh | bash
RUN apt update && apt install -y git git-lfs

WORKDIR /space/

ENV pip_mirror="-i https://mirrors.aliyun.com/pypi/simple"
RUN pip install pip --upgrade ${pip_mirror}
RUN pip install gradio ${pip_mirror}
RUN pip install git+https://github.com/huggingface/transformers


ADD ./ChatGLM-6B /space/repo
RUN pip install -r /space/repo/requirements.txt ${pip_mirror}

EXPOSE 7860

CMD cd /space/repo && python app.py --share
