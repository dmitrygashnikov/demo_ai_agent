FROM node:20-alpine AS build
WORKDIR /app

# Make npm resilient to flaky/slow networks and DNS hiccups inside the build
# sandbox (root cause of the EAI_AGAIN failure was the build container not being
# able to resolve registry.npmjs.org). Explicit registry + aggressive retries.
RUN npm config set registry https://registry.npmjs.org/ \
    && npm config set fetch-retries 5 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set fetch-retry-maxtimeout 120000 \
    && npm config set fetch-timeout 600000

COPY package.json package-lock.json* ./

# Use a reproducible install when a lockfile is present (npm ci), otherwise fall
# back to npm install. Either way the retry settings above apply.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
