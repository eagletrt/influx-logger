import logger from "./logger"

export class Line {
  measurement: string
  tags: Record<string, string>
  fields: Record<string, LineFieldType>
  timestamp: number

  constructor(
    measurement: string,
    tags: Record<string, string>,
    fields: Record<string, LineFieldType>,
    timestamp: number
  ) {
    this.measurement = measurement
    this.tags = tags
    this.fields = fields
    this.timestamp = timestamp
  }

  static fromObject(
    obj: Record<string, LineFieldType>,
    measurement: string,
    tags: Record<string, string>
  ): Line {

    const timestamp = obj['_innerTimestamp']
    if (!timestamp || typeof timestamp !== 'string') {
      throw new Error('Missing or invalid timestamp')
    }

    const fields = Object.entries(obj)
      .filter(([key]) => key !== '_timestamp')
      .reduce<Record<string, LineFieldType>>((prev, [key, value]) => {
        prev[key] = value
        return prev
      }, {})

    return new Line(measurement, tags, fields, parseInt(timestamp))
  }

  toString(): string {
    const fieldsString = Object.entries(this.fields).map(([key, value]) => {
      if (typeof value === 'string') {
        return `${key}="${value}"`
      }
      else {
        return `${key}=${value}`
      }
    }).join(',')

    const tagsString = Object.entries(this.tags)
      .map(([key, value]) => `${key}=${value}`).join(',')

    return `${this.measurement}${Object.keys(this.tags).length > 0 ? ',' : ''}${tagsString} ${fieldsString} ${this.timestamp}`
  }

}

export class LineRepository {
  private lines: Line[] = []
  private limit: number 

  constructor(limit: number) {
    this.limit = limit
  }

  async push(line: Line) {
    this.lines.push(line)
    if (this.lines.length >= this.limit) {
      await this.commit()
      this.lines = []
    }
  }

  private async commit() {
    logger.info(`Committing ${this.lines.length} lines`) 
  } 

  packLines(
    lines: Line[],
  ): string {
    return lines.map(line => line.toString()).join('\n')
  }
}

export type LineFieldType = string | number | boolean

