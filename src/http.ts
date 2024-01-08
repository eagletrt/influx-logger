const CAN_PROTO_URL: string = 'https://raw.githubusercontent.com/eagletrt/can/hash/proto/network/network.proto'
const CAN_COMMIT_URL: string = 'https://github.com/eagletrt/can/tree/hash'

export async function checkCommitExistance(hash: string): Promise<boolean> {
  const url = CAN_COMMIT_URL.replace(/hash/g, hash)
  const response = await fetch(url)
  return response.ok
}

export async function downloadProtoVersion(hash: string, network: string): Promise<string> {
  const url = CAN_PROTO_URL.replace(/hash/g, hash).replaceAll(/network/g, network)
  const response = await fetch(url)
  if (!response.ok) {
    throw Error()
  }
  return await response.text()
}
