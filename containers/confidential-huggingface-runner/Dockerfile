FROM python:3.10-slim as ipex_base

RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN pip install intel-extension-for-pytorch==2.2.0 oneccl_bind_pt --trusted-host ipex-1711374217.us-west-2.elb.amazonaws.com --extra-index-url https://ipex-1711374217.us-west-2.elb.amazonaws.com/release-whl/stable/cpu/us/

FROM ipex_base as model_cache

ARG model_id
RUN pip install huggingface_hub ${pip_mirror}
RUN huggingface-cli download --resume-download --repo-type model ${model_id}

FROM model_cache

ARG repo
ARG huggingface_space=""
ARG pip_mirror
ARG model_id
ENV MODEL_ID=${model_id}
ENV MODEL_HUB=/models/
RUN curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.deb.sh | bash
RUN apt update && apt install -y git git-lfs

WORKDIR /space/

ADD confidential-ai-loader /space/confidential-ai-loader
RUN pip install -r /space/confidential-ai-loader/requirements.txt
RUN pip install /space/confidential-ai-loader/
RUN pip install pip --upgrade ${pip_mirror}
RUN pip install gradio ${pip_mirror}
RUN pip install git+https://github.com/huggingface/transformers
RUN git clone ${repo} repo

RUN pip install -r /space/repo/requirements.txt ${pip_mirror}

EXPOSE 7860

CMD cd /space/repo && hf_loader python app.py --share
