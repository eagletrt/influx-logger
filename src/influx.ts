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

    const timestamp = obj._timestamp

    if (!timestamp || typeof timestamp !== 'number') {
      throw new Error('Timestamp is required')
    }

    const fields = Object.entries(obj)
      .filter(([key]) => key !== '_timestamp')
      .reduce<Record<string, LineFieldType>>((prev, [key, value]) => {
        prev[key] = value
        return prev
      }, {})

    return new Line(measurement, tags, fields, timestamp)
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

  static packLines(
    lines: Line[],
  ): string {
    return lines.map(line => line.toString()).join('\n')
  }
}

export type LineFieldType = string | number | boolean

