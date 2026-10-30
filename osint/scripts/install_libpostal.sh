#!/bin/sh
# Pinned upstream source; model data remains inside the Docker image.
set -eu
revision=25099c506612b34b23b1bfe286ca6321fcf06f35
apt-get update
apt-get install -y --no-install-recommends autoconf automake libtool pkg-config curl ca-certificates build-essential git
mkdir -p /tmp/menace-libpostal
cd /tmp/menace-libpostal
git init
git remote add origin https://github.com/openvenues/libpostal.git
git fetch --depth 1 origin "$revision"
git checkout --detach FETCH_HEAD
./bootstrap.sh
./configure --disable-sse2 --datadir=/usr/local/share
make -j2
make install
ldconfig
pip install --no-cache-dir postal==1.1.11
cd /
rm -rf /tmp/menace-libpostal /var/lib/apt/lists/*
