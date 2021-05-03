FROM amazonlinux:2 as build

SHELL ["/bin/bash", "-euxo", "pipefail", "-c"]

# hadolint ignore=SC2211
RUN amazon-linux-extras enable python3.8; \
    curl --proto '=https' --tlsv1.2 -fsSL https://rpm.nodesource.com/setup_15.x | bash -; \
    yum install -y \
      # provides /usr/bin/strip
      binutils-2.29.* \
      jq-1.5-* \
      nodejs-2:15.14.* \
      python38-3.8.* \
      zip-3.0-*; \
    yum clean all; \
    pip3.8 install --no-cache-dir -U pip==21.0.*; \
    npm install -g npm@7.10.0; \
    npm install -g yarn@1.22.10; \
    npm cache clean --force; \
    mkdir /src /work /out

WORKDIR /src

COPY . .

RUN yarn install; \
    yarn run build; \
    yarn cache clean; \
    pip3.8 install --no-cache-dir --disable-pip-version-check -r <(./gen-requirements.sh) --target /work; \
    cp -pr webpack.config.js yarn.lock package.json ./*.py src common dist /work; \
    find /work -name \*.so -exec strip --verbose --strip-unneeded --preserve-dates {} \;

WORKDIR /work

ARG VERSION=latest
RUN printf "app_version = \"%s\"" "$VERSION" > version.py; \
    zip -qr9 /opt/sari-web.zip .

FROM alpine:3.13

COPY --from=build /opt /opt
