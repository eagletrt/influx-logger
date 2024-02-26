FROM oven/bun:slim as modules_installer
COPY package.json .
RUN bun install 

FROM modules_installer
COPY src/ src/

CMD bun run start -- /configuration.json
