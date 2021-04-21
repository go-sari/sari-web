FROM amazonlinux:2

RUN amazon-linux-extras enable python3.8

RUN set -eux; \
    yum install -y \
      binutils \
      jq \
      python3.8 \
      zip; \
    pip3.8 install -U pip

RUN set -eux; \
    curl --proto '=https' --tlsv1.2 -fsSL https://rpm.nodesource.com/setup_15.x | bash -; \
    yum install -y nodejs; \
    npm install -g npm; \
    npm install -g yarn

RUN mkdir /src /work /out

WORKDIR /src

COPY . .

RUN set -eux; \
    yarn install; \
    yarn run build; \
    ./gen-requirements.sh > /tmp/requirements.txt; \
    pip install -r /tmp/requirements.txt --target /work; \
    cp -pr webpack.config.js yarn.lock package.json *.py src common dist /work; \
    find /work -name \*.so -exec strip --verbose --strip-unneeded --preserve-dates {} \;

WORKDIR /work

ARG VERSION=latest
RUN printf "app_version = \"$VERSION\"" > version.py

CMD ["zip", "-qr9", "/out/sari-web.zip", "."]

