import logger from "./logger";

export class Line {
  measurement: string;
  tags: Record<string, string>;
  fields: Record<string, LineFieldType>;
  timestamp: number;

  constructor(
    measurement: string,
    tags: Record<string, string>,
    fields: Record<string, LineFieldType>,
    timestamp: number
  ) {
    this.measurement = measurement;
    this.tags = tags;
    this.fields = fields;
    this.timestamp = timestamp;
  }

  static fromObject(
    obj: Record<string, LineFieldType>,
    measurement: string,
    tags: Record<string, string>
  ): Line {
    const timestamp = obj["_innerTimestamp"];
    if (!timestamp || typeof timestamp !== "string") {
      throw new Error("Missing or invalid timestamp");
    }

    const fields = Object.entries(obj)
      .filter(([key]) => key !== "_timestamp")
      .reduce<Record<string, LineFieldType>>((prev, [key, value]) => {
        prev[key] = value;
        return prev;
      }, {});

    return new Line(measurement, tags, fields, parseInt(timestamp));
  }

  toString(): string {
    const fieldsString = Object.entries(this.fields)
      .map(([key, value]) => {
        if (typeof value === "string") {
          return `${key}="${value}"`;
        } else {
          return `${key}=${value}`;
        }
      })
      .join(",");

    const tagsString = Object.entries(this.tags)
      .map(([key, value]) => `${key}=${value}`)
      .join(",");

    return `${this.measurement}${
      Object.keys(this.tags).length > 0 ? "," : ""
    }${tagsString} ${fieldsString} ${this.timestamp}`;
  }
}

export class LineRepository {
  private lines: Line[] = [];
  private limit: number;
  private url: string;
  private token: string;
  private org: string;
  private timestampPrecision: "ns" | "us" | "ms" | "s";
  private prendingCommitsCount: number = 0;

  constructor(
    url: string,
    org: string,
    token: string,
    timestampPrecision: "ns" | "us" | "ms" | "s" = "ns",
    limit: number
  ) {
    this.url = url;
    this.token = token;
    this.org = org;
    this.timestampPrecision = timestampPrecision;
    this.limit = limit;
  }

  async push(line: Line, bucket: string) {
    this.lines.push(line);
    if (this.lines.length >= this.limit) {
      await this.commit();
      this.lines = [];
    }
  }

  private async commit(bucket: string) {
    const linesCount = this.lines.length;
    logger.info(`Committing ${linesCount} lines`);
    logger.info(`Pending commits: ${this.prendingCommitsCount}`);
    this.prendingCommitsCount += 1;

    const pack = LineRepository.packLines(this.lines);
    const url = `${this.url}/api/v2/write?org=${this.org}&bucket=${this.bucket}&precision=${this.timestampPrecision}`;

    const response = await fetch(url, {
      method: "POST",
      body: pack,
      headers: {
        Authorization: `Token ${this.token}`,
      },
    });

    if (!response.ok) {
      const text = await response.text();
      logger.error(`Failed to commit lines: ${text}`);
    } else {
      logger.info(`Committed ${linesCount} lines`);
    }

    this.prendingCommitsCount -= 1;
  }

  static packLines(lines: Line[]): string {
    return lines.map((line) => line.toString()).join("\n");
  }
}

export type LineFieldType = string | number | boolean;
