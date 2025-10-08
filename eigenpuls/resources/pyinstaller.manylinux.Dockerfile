FROM quay.io/pypa/manylinux2014_x86_64

ARG PY_VER=3.11.9
ENV PY_PREFIX=/opt/python311
ARG OPENSSL_VER=1.1.1w
ENV OPENSSL_PREFIX=/opt/openssl-${OPENSSL_VER}

RUN yum -y update && yum -y install \
    gcc gcc-c++ make \
    openssl-devel bzip2-devel libffi-devel zlib-devel xz-devel \
    sqlite-devel readline-devel tk-devel uuid-devel \
    curl tar \
    && yum clean all

# Build OpenSSL (to provide modern SSL for Python)
RUN curl -fsSL https://www.openssl.org/source/openssl-${OPENSSL_VER}.tar.gz -o /tmp/openssl-${OPENSSL_VER}.tar.gz && \
    tar -xzf /tmp/openssl-${OPENSSL_VER}.tar.gz -C /tmp && \
    cd /tmp/openssl-${OPENSSL_VER} && \
    ./config enable-shared no-tests --prefix=${OPENSSL_PREFIX} && \
    make -j"$(nproc)" && make install_sw && \
    rm -rf /tmp/openssl-${OPENSSL_VER}*

# Build CPython with shared lib and OpenSSL
RUN curl -fsSL https://www.python.org/ftp/python/${PY_VER}/Python-${PY_VER}.tgz -o /tmp/Python-${PY_VER}.tgz && \
    tar -xzf /tmp/Python-${PY_VER}.tgz -C /tmp && \
    cd /tmp/Python-${PY_VER} && \
    CPPFLAGS="-I${OPENSSL_PREFIX}/include" \
    LDFLAGS="-L${OPENSSL_PREFIX}/lib" \
    LD_LIBRARY_PATH="${OPENSSL_PREFIX}/lib" \
    ./configure --prefix=${PY_PREFIX} --enable-shared --enable-optimizations --with-openssl=${OPENSSL_PREFIX} && \
    make -j"$(nproc)" && make install && \
    ln -sf ${PY_PREFIX}/bin/python3 ${PY_PREFIX}/bin/python && \
    rm -rf /tmp/Python-${PY_VER}* 

ENV PATH=${PY_PREFIX}/bin:${PATH}
ENV LD_LIBRARY_PATH=${PY_PREFIX}/lib:${OPENSSL_PREFIX}/lib:${LD_LIBRARY_PATH}

RUN python -m pip install --upgrade pip

WORKDIR /

ENV PATH=/opt/python/cp311-cp311/bin:${PATH}
RUN python3.11 -m ensurepip && python3.11 -m pip install --upgrade pip

ENTRYPOINT ["/bin/bash", "-lc"]

