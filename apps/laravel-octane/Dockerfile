# syntax=docker/dockerfile:1
ARG PHP_IMAGE=php:8.3-cli-bookworm
ARG COMPOSER_IMAGE=composer:2

# ---- PHP extensions (needs build tools; only the compiled result is copied on) ----
FROM ${PHP_IMAGE} AS ext
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev $PHPIZE_DEPS \
 && docker-php-ext-install pdo_pgsql opcache pcntl \
 && pecl install -D 'enable-brotli="no" enable-zstd="no" enable-swoole-curl="no" enable-cares="no" enable-openssl="no" enable-sockets="no" enable-mysqlnd="no" enable-swoole-pgsql="no" enable-swoole-sqlite="no" enable-swoole-thread="no" enable-iouring="no"' swoole && docker-php-ext-enable swoole \
 && rm -rf /var/lib/apt/lists/*

# ---- dependencies ----
FROM ${COMPOSER_IMAGE} AS vendor
WORKDIR /app
COPY composer.json composer.lock* ./
RUN composer install --no-dev --no-scripts --no-autoloader --prefer-dist --no-progress --ignore-platform-reqs
COPY . .
RUN composer dump-autoload --no-dev --classmap-authoritative --no-scripts --ignore-platform-reqs

# ---- runtime ----
FROM ${PHP_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 procps \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ext /usr/local/lib/php/extensions /usr/local/lib/php/extensions
COPY --from=ext /usr/local/etc/php/conf.d /usr/local/etc/php/conf.d
COPY docker/php.ini /usr/local/etc/php/conf.d/zz-bench.ini
COPY --from=vendor --chown=www-data:www-data /app /app
RUN mkdir -p /app/bootstrap/cache /app/storage/framework/cache /app/storage/framework/views /app/storage/framework/sessions /app/storage/logs \
 && chown -R www-data:www-data /app/bootstrap/cache /app/storage \
 && chmod +x /app/docker/entrypoint.sh
ENV APP_ENV=production APP_DEBUG=false APP_KEY=base64:MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY= \
    OCTANE_SERVER=swoole OCTANE_WORKERS=4 TZ=Asia/Kolkata
WORKDIR /app
USER www-data
EXPOSE 8080
STOPSIGNAL SIGTERM
ENTRYPOINT ["/app/docker/entrypoint.sh"]
