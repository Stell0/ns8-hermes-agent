#!/bin/bash

#
# Copyright (C) 2023 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-3.0-or-later
#

# Terminate on error
set -e

# Prepare variables for later use
images=()
# The image will be pushed to GitHub container registry
repobase="${REPOBASE:-ghcr.io/nethserver}"
# Normalize the tag so branch names remain valid image tags.
imagetag="${IMAGETAG:-latest}"
imagetag="${imagetag//\//-}"
# Configure the image name
reponame="hermes-agent"

build_component_image() {
    local image_name="$1"
    local context_dir="$2"

    echo "Build ${image_name} container..."
    buildah build \
        --force-rm \
        --layers \
        --jobs "$(nproc)" \
        --ulimit nofile=65536:65536 \
        --tag "${repobase}/${image_name}" \
        --tag "${repobase}/${image_name}:${imagetag}" \
        "${context_dir}"

    images+=("${repobase}/${image_name}")
}

component_images=(
    "${repobase}/hermes-agent-auth:${imagetag}"
    "${repobase}/hermes-agent-hermes:${imagetag}"
    "${repobase}/hermes-agent-socket:${imagetag}"
)

# Create a new empty container image
container=$(buildah from scratch)

# Reuse existing nodebuilder-hermes-agent container, to speed up builds
if ! buildah containers --format "{{.ContainerName}}" | grep -q nodebuilder-hermes-agent; then
    echo "Pulling NodeJS runtime..."
    buildah from --name nodebuilder-hermes-agent -v "${PWD}:/usr/src:Z" docker.io/library/node:24.11.1-slim
fi

echo "Build static UI files with node..."
buildah run \
    --workingdir=/usr/src/ui \
    --env="NODE_OPTIONS=--openssl-legacy-provider" \
    nodebuilder-hermes-agent \
    sh -c "yarn install && yarn build"

build_component_image "hermes-agent-auth" "containers/auth"
build_component_image "hermes-agent-hermes" "containers/hermes"
build_component_image "hermes-agent-socket" "containers/socket"

# Add imageroot directory to the container image
buildah add "${container}" imageroot /imageroot
buildah add "${container}" ui/dist /ui
# Setup the entrypoint and set a rootless container
buildah config --entrypoint=/ \
    --label="org.nethserver.authorizations=cluster:accountconsumer traefik@node:routeadm node:portsadm" \
    --label="org.nethserver.tcp-ports-demand=1" \
    --label="org.nethserver.rootfull=0" \
    --label="org.nethserver.images=${component_images[*]}" \
    "${container}"
# Commit the image
buildah commit "${container}" "${repobase}/${reponame}"
buildah commit "${container}" "${repobase}/${reponame}:${imagetag}"

# Append the image URL to the images array
images+=("${repobase}/${reponame}")

#
# NOTICE:
#
# It is possible to build and publish multiple images.
#
# 1. create another buildah container
# 2. add things to it and commit it
# 3. append the image url to the images array
#

#
# Setup CI when pushing to Github. 
# Warning! docker::// protocol expects lowercase letters (,,)
if [[ -n "${CI}" ]]; then
    # Set output value for Github Actions
    printf "images=%s\n" "${images[*],,}" >> "${GITHUB_OUTPUT}"
else
    # Just print info for manual push
    printf "Publish the images with:\n\n"
    for image in "${images[@],,}"; do printf "  buildah push %s docker://%s:%s\n" "${image}" "${image}" "${imagetag}" ; done
    printf "\n"
fi
