import pino from "pino";

export default pino({
  level: process.env.NODE_ENV === "development" ? "trace" : "info",
  transport: {
    target: "pino-pretty",
    options: {
      colorize: true,
    },
  },
});
