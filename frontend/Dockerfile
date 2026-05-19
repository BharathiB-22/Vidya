# ── Stage 1: build ────────────────────────────────────────────────────────────
# Pinned to a specific digest for reproducible builds.
# To update: docker manifest inspect node:20-alpine | grep digest
FROM node:20-alpine@sha256:afdf98210b07b586eb71fa22ba2e432e058e4cd1304d31ed60888755b8c865fb AS builder

WORKDIR /build

# Install dependencies from lockfile before copying source so this layer
# is cached until package-lock.json changes.
COPY package.json package-lock.json ./
# Install all deps (including devDependencies) — tsc and vite are dev-only
# tools required to compile.  The runtime stage (Nginx) copies only dist/
# so node_modules never reaches the production image.
RUN npm ci

# Copy source and build.  tsc + vite build outputs to dist/.
COPY . .
RUN npm run build


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
# Pinned to a specific digest.
# To update: docker manifest inspect nginx:1.27-alpine | grep digest
FROM nginx:1.27-alpine@sha256:62223d644fa234c3a1cc785ee14242ec47a77364226f1c811d2f669f96dc2ac8 AS runtime

# Non-root system user — no home directory, no interactive shell.
RUN adduser -D -u 1001 -s /sbin/nologin vidya

# Copy built assets and Nginx config as root, then assign ownership.
COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

# Remove the default virtual host — our nginx.conf replaces the full config
# and the entrypoint script would otherwise try to modify this file on start.
RUN rm -f /etc/nginx/conf.d/default.conf

# Grant our non-root user write access to all directories Nginx needs at
# runtime.  Temp paths are configured to /tmp in nginx.conf (world-writable
# by default) so they need no explicit chown.
RUN chown -R vidya:vidya /usr/share/nginx/html \
    && chown -R vidya:vidya /var/cache/nginx \
    && chown -R vidya:vidya /var/log/nginx

USER vidya

EXPOSE 3000

# Health: fetch the root page.  --spider sends HEAD to avoid downloading the
# full body while still verifying Nginx responds with 2xx.
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost:3000/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
