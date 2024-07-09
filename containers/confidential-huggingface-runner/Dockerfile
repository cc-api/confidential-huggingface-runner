FROM python:3.11-slim AS ipex_base

RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN pip install intel-extension-for-pytorch oneccl_bind_pt --trusted-host ipex-1711374217.us-west-2.elb.amazonaws.com --extra-index-url https://ipex-1711374217.us-west-2.elb.amazonaws.com/release-whl/stable/cpu/us/

FROM ipex_base AS model_cache

ARG model_id
RUN pip install huggingface_hub ${pip_mirror}
RUN huggingface-cli download --resume-download --repo-type model ${model_id}

FROM node:20 AS pnpm_base
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
ARG DEBIAN_FRONTEND=noninteractive
RUN corepack enable && pnpm i -g pnpm@9.1.0
RUN apt update && apt install -y git python3-pip python3-venv
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"
RUN git clone https://github.com/dongx1x/gradio && cd gradio && \
    bash scripts/install_gradio.sh && bash ./scripts/build_frontend.sh
RUN cd gradio && pip install build && python3 -m build

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
RUN pip install pip --upgrade ${pip_mirror}
RUN pip install -r /space/confidential-ai-loader/requirements.txt
RUN pip install /space/confidential-ai-loader/
RUN git clone ${repo} repo
RUN pip install -r /space/repo/requirements.txt ${pip_mirror}
COPY --from=pnpm_base /gradio/dist/*.whl ./
RUN pip install --force-reinstall ./*.whl
RUN pip install --force-reinstall git+https://github.com/dongx1x/fastapi

EXPOSE 7860

CMD cd /space/repo && hf_loader python app.py --share
