# syntax = docker/dockerfile:experimental

FROM amazonlinux:2 as build

RUN amazon-linux-extras enable python3.8
RUN yum install -y \
    binutils \
    jq \
    python3.8 \
    zip

COPY gen-requirements.sh filter-pkgs.awk Pipfile Pipfile.lock src/
WORKDIR src

RUN ./gen-requirements.sh > /tmp/requirements.txt
RUN set -eux; \
    pip3.8 install -U pip; \
    pip3.8 install -r /tmp/requirements.txt --target .
RUN find . -name \*.so \
    -exec strip --verbose --strip-unneeded --preserve-dates {} \;

COPY . .

ARG archive_name=sari-web-LATEST.zip
RUN zip -qr9 /opt/$archive_name .

FROM scratch
COPY --from=build /opt /
