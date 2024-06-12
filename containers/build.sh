#!/bin/bash

set -e

current_directory=$(readlink -f "$(dirname "${BASH_SOURCE[0]}")")
top_directory=$(dirname "${current_directory}")
container_directory="${top_directory}/containers"
action="all"
registry="registry.cn-hangzhou.aliyuncs.com/kenplusplus"
container="all"
tag="latest"
docker_build_clean_param=""
model_id="dongx1x/Llama-2-7b-chat-hf-sharded-bf16-aes"
all_containers=()

function info {
    local msg="${1:-}"

    echo -e "INFO: $msg"
}

function error {
    local msg="${1:-}"

    echo >&2 -e "ERROR: $msg"
}

function die {
    local msg="${1:-}"

    error "$msg"

    exit 1
}

function scan_all_containers {
    mapfile -t dirs < <(cd "${container_directory}" && ls -d ./*/)
    for dir in "${dirs[@]}"
    do
        dir=${dir#./}
        all_containers+=("${dir::-1}")
    done
}

function usage {
    cat << EOM
usage: $(basename "$0") [OPTION]...
    -a <build|download|publish|save|all>  all is default, which not include save. Please execute save explicity if need.
    -c <container name> same as directory name.
    -f Clean build.
    -g <tag> container image tag.
    -h Show usage.
    -m <model name> name of a model which will be cached inside the container image.
    -p <repo name> name of a hugging face repo which will be set as the default application.
    -r <registry prefix> the prefix string for registry.
EOM
    exit 1
}

function process_args {
while getopts ":a:c:g:hm:p:r:" option; do
        case "${option}" in
            a) action="${OPTARG}";;
            c) container="${OPTARG}";;
            f) docker_build_clean_param="--no-cache --rm";;
            g) tag="${OPTARG}";;
            h) usage;;
            m) model_id="${OPTARG}";;
            p) repo="${OPTARG}";;
            r) registry="${OPTARG}";;
            *) error "Invalid option: -${OPTARG}"
               usage
               ;;
        esac
    done

    [ -z "$model_id" ] && die "need model ID"
    [ -z "$repo" ] && die "need repo"

    if [[ ! "$action" =~ ^(build|download|publish|save|all)$ ]]; then
        error "invalid type: $action"
        usage
    fi

    if [ "$container" != 'all' ]; then
        if [[ ! "${all_containers[*]}" =~ ${container} ]]; then
            error "invalid container name: $container"
            usage
        fi
    fi

    if [ -z "$registry" ]; then
        if [ -z "$EIP_REGISTRY" ]; then
            die "Please specify your docker registry via -r <registry prefix> or set environment variable EIP_REGISTRY."
        else
            registry=$EIP_REGISTRY
        fi
    fi
}

function build_a_image {
    local img_container="${1:-}"
    [ -z "$img_container" ] && die "need container image"

    info "Build container image => ${registry}/${img_container}:${tag}"

    if [ -f "${container_directory}/${img_container}/pre-build.sh" ]; then
        info "Execute pre build script at ${container_directory}/${img_container}/pre-build.sh"
        "${container_directory}/${img_container}/pre-build.sh" || { die 'Failed to execute pre-build.sh'; }
    fi

    docker_build_args=(
        "--build-arg" "hf_token"
        "--build-arg" "http_proxy"
        "--build-arg" "https_proxy"
        "--build-arg" "model_id=${model_id}"
        "--build-arg" "no_proxy"
        "--build-arg" "pip_mirror"
        "--build-arg" "repo=${repo}"
        "-f" "${container_directory}/${img_container}/Dockerfile"
        .
        "--tag" "${registry}/${img_container}:${tag}"
    )

    if [ -n "${docker_build_clean_param}" ]; then
        read -ar split_params <<< "${docker_build_clean_param}"
        docker_build_args+=("${split_params[@]}")
    fi

    pushd "${container_directory}/${img_container}"
    info "PWD: '$PWD'"
    docker build "${docker_build_args[@]}" || \
        { die "Failed to build docker ${registry}/${img_container}:${tag}"; }
    popd

    info "Complete build image => ${registry}/${img_container}:${tag}"

    if [ -f "${container_directory}/${img_container}/post-build.sh" ]; then
        info "Execute post build script at ${container_directory}/${img_container}/post-build.sh"
        "${container_directory}/${img_container}/post-build.sh" || { die "Failed to execute post-build.sh"; }
    fi

    echo -e "\n\n"
}

function build_images {
    if [ "$container" = 'all' ]; then
        for img_container in "${all_containers[@]}"
        do
            build_a_image "$img_container"
        done
    else
        build_a_image "$container"
    fi
}

function publish_a_image {
    local img_container="${1:-}"
    [ -z "$img_container" ] && die "need container image"

    info "Publish container image: ${registry}/${img_container}:${tag} ..."
    docker push "${registry}/${img_container}:${tag}" || \
        { die "Failed to push docker ${registry}/${img_container}:${tag}"; }
    info "Complete publish container image ${registry}/${img_container}:${tag} ...\n"
}

function publish_images {
    if [ "$container" = 'all' ]; then
        for img_container in "${all_containers[@]}"
        do
            publish_a_image "$img_container"
        done
    else
        publish_a_image "$container"
    fi
}

function download_a_image {
    local img_container="${1:-}"
    [ -z "$img_container" ] && die "need container image"

    info "Download container image: ${registry}/${img_container}:${tag} ..."
    crictl pull "${registry}/${img_container}:${tag}" || \
        { die "Failed to download images ${registry}/${img_container}:${tag}"; }
    info "Complete download container image ${registry}/${img_container}:${tag} ...\n"
}

function download_images {
    if [ "$container" = 'all' ]; then
        for img_container in "${all_containers[@]}"
        do
            download_a_image "$img_container"
        done
    else
        download_a_image "$container"
    fi
}

function save_a_image {
    local img_container="${1:-}"
    [ -z "$img_container" ] && die "need container image"

    info "Save container image ${registry}/${img_container}:${tag} => ${top_directory}/images/ ... "
    mkdir -p "${top_directory}/images/"
    docker save -o "${top_directory}/images/${img_container}-${tag}.tar" "${registry}/${img_container}:${tag}"
    docker save "${registry}/${img_container}:${tag}" | gzip > "${top_directory}/images/${img_container}-${tag}.tgz"
}

function save_images {
    if [ "$container" = 'all' ]; then
        for img_container in "${all_containers[@]}"
        do
            save_a_image "$img_container"
        done
    else
        save_a_image "$container"
    fi
}

function check_docker {
    if ! command -v docker &> /dev/null
    then
        die "Docker could not be found. Please install Docker."
    fi
}

check_docker
scan_all_containers
process_args "$@"

info ""
info "-------------------------"
info "action: ${action}"
info "container: ${container}"
info "tag: ${tag}"
info "registry: ${registry}"
info "-------------------------"
info ""

if [[ "$action" =~ ^(build|all)$ ]]; then
    build_images
fi

if [[ "$action" =~ ^(publish|all)$ ]]; then
    publish_images
fi

if [[ "$action" =~ ^(save)$ ]]; then
    save_images
fi

if [[ "$action" =~ ^(download)$ ]]; then
    download_images
fi
