# pickfit on Google Cloud Run: the Worker's code (src/) behind a Node server (cloudrun/server.ts).
# Build from worker/ after `npm run build:index`, which writes src/generated/ (see cloudrun/README.md).
FROM node:24-slim
ENV NODE_ENV=production
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts
COPY wrangler.jsonc ./
COPY public ./public
COPY src ./src
COPY cloudrun ./cloudrun
USER node
EXPOSE 8080
CMD ["node", "cloudrun/server.ts"]
