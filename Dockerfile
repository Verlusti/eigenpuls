# --- Variables ---

ARG PY_VER=3.11.9
ARG PY_VER_SHORT=3.11
ARG PY_PREFIX=/opt/python311
ARG OPENSSL_VER=1.1.1w
ARG OPENSSL_PREFIX=/opt/openssl-${OPENSSL_VER}


# --- Build Stage ---

# This stage has all the tools needed to compile everything.
FROM quay.io/pypa/manylinux2014_x86_64 AS builder
ARG PY_VER
ARG PY_VER_SHORT
ARG PY_PREFIX
ARG OPENSSL_VER
ARG OPENSSL_PREFIX
ENV PATH=${PY_PREFIX}/bin:${PATH}
ENV LD_LIBRARY_PATH=${PY_PREFIX}/lib:${OPENSSL_PREFIX}/lib:${LD_LIBRARY_PATH}

# Install all build dependencies
RUN yum -y update && yum -y install \
    gcc gcc-c++ make \
    openssl-devel bzip2-devel libffi-devel zlib-devel xz-devel \
    sqlite-devel readline-devel tk-devel uuid-devel gdbm-devel \
    curl tar \
    && yum clean all

# Build OpenSSL
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
    rm -rf /tmp/Python-${PY_VER}*

WORKDIR /app

RUN python${PY_VER_SHORT} -m ensurepip && python${PY_VER_SHORT} -m pip install --upgrade pip wheel ultradict atomics

# Install application and server deps in builder
COPY pyproject.toml README.md /app/
COPY eigenpuls /app/eigenpuls
COPY eigenpulsd /app/eigenpulsd
RUN python${PY_VER_SHORT} -m pip install --no-cache-dir '.[server]'

# Prune Python tree in builder to shrink what we copy to final
RUN rm -rf \
        ${PY_PREFIX}/lib/python${PY_VER_SHORT}/test \
        ${PY_PREFIX}/lib/python${PY_VER_SHORT}/tkinter \
        ${PY_PREFIX}/lib/python${PY_VER_SHORT}/idlelib \
        ${PY_PREFIX}/lib/python${PY_VER_SHORT}/lib2to3 \
        ${PY_PREFIX}/lib/python${PY_VER_SHORT}/ensurepip \
        ${PY_PREFIX}/lib/python${PY_VER_SHORT}/pydoc_data \
        ${PY_PREFIX}/share \
        ${PY_PREFIX}/lib/pkgconfig \
    && find ${PY_PREFIX} -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && find ${PY_PREFIX} -type f -name '*.pyc' -delete \
    && (command -v strip >/dev/null 2>&1 && find ${PY_PREFIX} -type f -name '*.so' -exec strip --strip-unneeded {} + || true) \
    && (command -v strip >/dev/null 2>&1 && strip --strip-unneeded ${PY_PREFIX}/bin/python${PY_VER_SHORT} || true)


# --- Final Stage ---

# This stage is clean. We only copy the necessary artifacts from the builder.
FROM debian:bookworm-slim AS final
ARG PY_VER
ARG PY_PREFIX
ARG PY_VER_SHORT
ARG OPENSSL_VER
ARG OPENSSL_PREFIX
ENV PATH=${PY_PREFIX}/bin:${PATH}
ENV LD_LIBRARY_PATH=${PY_PREFIX}/lib:${OPENSSL_PREFIX}/lib:/usr/local/lib:${LD_LIBRARY_PATH}

# Add minimal runtime libs and shell tools (include libatomic1 for atomics wheel)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl libffi8 zlib1g libbz2-1.0 liblzma5 libsqlite3-0 \
    libuuid1 tk libreadline8 libgdbm6 libnsl-dev libatomic1 tini bash binutils && \
    rm -rf /var/lib/apt/lists/*

# Copy only the runtime dependencies (like OpenSSL and Python's own shared libs)
COPY --from=builder /usr/lib64/libffi.so.6* /usr/local/lib/
COPY --from=builder /usr/lib64/libreadline.so.6* /usr/local/lib/
COPY --from=builder /lib64/libtinfo.so.5* /usr/local/lib/
COPY --from=builder ${OPENSSL_PREFIX}/lib/libssl.so* /usr/local/lib/
COPY --from=builder ${OPENSSL_PREFIX}/lib/libcrypto.so* /usr/local/lib/
RUN mkdir -p ${PY_PREFIX}/bin ${PY_PREFIX}/lib ${PY_PREFIX}/lib/python${PY_VER_SHORT}
COPY --from=builder ${PY_PREFIX}/bin/python${PY_VER_SHORT} ${PY_PREFIX}/bin/
COPY --from=builder ${PY_PREFIX}/lib/libpython${PY_VER_SHORT}.so* ${PY_PREFIX}/lib/
COPY --from=builder ${PY_PREFIX}/lib/python${PY_VER_SHORT} ${PY_PREFIX}/lib/python${PY_VER_SHORT}

# Copy the installed application
COPY --from=builder /app /app

WORKDIR /app

# App already installed in builder site-packages; no pip in final

# Sanity check: ensure ultradict imports with the runtime interpreter
RUN ${PY_PREFIX}/bin/python${PY_VER_SHORT} - <<'PY'
import sys
try:
    import UltraDict
    print('UltraDict OK:', UltraDict.__file__)
    print('Python:', sys.executable)
except Exception as e:
    print('UltraDict import failed:', e)
    raise
PY

# Final stage cleanup to reduce size
ENV LD_LIBRARY_PATH=/usr/local/lib:${PY_PREFIX}/lib:${LD_LIBRARY_PATH}

# Start app
EXPOSE 4242
CMD ["/opt/python311/bin/python3.11", "eigenpulsd", "serve"]