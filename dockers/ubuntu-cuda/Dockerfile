# Copyright The Lightning AI team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

ARG UBUNTU_VERSION=22.04
ARG CUDA_VERSION=11.7.0
ARG CUDNN_VERSION=8
# select devel | runtime
ARG IMAGE_TYPE=devel


FROM nvidia/cuda:${CUDA_VERSION}-cudnn${CUDNN_VERSION}-${IMAGE_TYPE}-ubuntu${UBUNTU_VERSION}

ARG PYTHON_VERSION=3.10

SHELL ["/bin/bash", "-c"]
# https://techoverflow.net/2019/05/18/how-to-fix-configuring-tzdata-interactive-input-when-building-docker-images/
ENV \
    DEBIAN_FRONTEND="noninteractive" \
    TZ="Etc/UTC" \
    PATH="$PATH:/root/.local/bin" \
    CUDA_TOOLKIT_ROOT_DIR="/usr/local/cuda" \
    MKL_THREADING_LAYER="GNU" \
    MAKEFLAGS="-j$(nproc)"

RUN \
    # TODO: Remove the manual key installation once the base image is updated.
    # https://github.com/NVIDIA/nvidia-docker/issues/1631
    # https://github.com/NVIDIA/nvidia-docker/issues/1631#issuecomment-1264715214
    apt-get update && apt-get install -y wget && \
    wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2004/x86_64/3bf863cc.pub && \
    mkdir -p /etc/apt/keyrings/ && mv 3bf863cc.pub /etc/apt/keyrings/ && \
    echo "deb [signed-by=/etc/apt/keyrings/3bf863cc.pub] https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/ /" /etc/apt/sources.list.d/cuda.list && \
    apt-get update -qq --fix-missing && \
    NCCL_VER=$(dpkg -s libnccl2 | grep '^Version:' | awk -F ' ' '{print $2}' | awk -F '-' '{print $1}' | grep -ve '^\s*$') && \
    CUDA_VERSION_MM=${CUDA_VERSION%.*} && \
    TO_INSTALL_NCCL=$(echo -e "$MAX_ALLOWED_NCCL\n$NCCL_VER" | sort -V  | head -n1)-1+cuda${CUDA_VERSION_MM} && \
    apt-get install -y --no-install-recommends --allow-downgrades --allow-change-held-packages \
        build-essential \
        ca-certificates \
        software-properties-common \
        pkg-config \
        cmake \
        git \
        wget \
        curl \
        unzip \
        libopenmpi-dev \
        openmpi-bin \
        graphviz \
        ssh && \
    # Install python
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get install -y \
        python${PYTHON_VERSION} \
        python${PYTHON_VERSION}-distutils \
        python${PYTHON_VERSION}-dev \
    && \
    update-alternatives --install /usr/bin/python${PYTHON_VERSION%%.*} python${PYTHON_VERSION%%.*} /usr/bin/python${PYTHON_VERSION} 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python${PYTHON_VERSION} 1 && \
    # Cleaning
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /root/.cache && \
    rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/

ENV PYTHONPATH="/usr/lib/python${PYTHON_VERSION}/site-packages"

RUN \
    curl https://bootstrap.pypa.io/get-pip.py | python${PYTHON_VERSION} && \
    CUDA_VERSION_MM=${CUDA_VERSION%.*} && \
    pip install -U -r requirements/base.txt -r requirements/test.txt \
      --find-links="https://download.pytorch.org/whl/cu${CUDA_VERSION_MM//'.'/''}" \
      --find-links="https://download.pytorch.org/whl/test/cu${CUDA_VERSION_MM//'.'/''}/torch_test.html" \
    && \
    rm -rf requirements/

RUN \
    # Show what we have
    pip --version && \
    pip list && \
    python -c "import sys; ver = sys.version_info ; assert f'{ver.major}.{ver.minor}' == '$PYTHON_VERSION', ver" && \
    python -c "import torch; print(torch.__version__)"