FROM node:26-slim AS deps
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM node:26-slim AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY frontend ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:26-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./
EXPOSE 3000
CMD ["npm", "start"]
