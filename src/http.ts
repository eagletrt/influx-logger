import logger from "./logger";
const CAN_PROTO_URL: string =
  "https://raw.githubusercontent.com/eagletrt/can/hash/proto/network/network.proto";
const CAN_COMMIT_URL: string = "https://github.com/eagletrt/can/tree/hash";

export async function checkCommitExistance(hash: string): Promise<boolean> {
  const url = CAN_COMMIT_URL.replace(/hash/g, hash);
  const response = await fetch(url);
  return response.ok;
}

export async function downloadProtoVersion(
  hash: string,
  network: string
): Promise<string> {
  const url = CAN_PROTO_URL.replace(/hash/g, hash).replaceAll(
    /network/g,
    network
  );
  const response = await fetch(url);
  if (!response.ok) {
    throw Error();
  }
  return await response.text();
}

export async function checkBucketExistance(_url: string, _bucket: string) {
  const url = `http://${_url}/api/v2/buckets`;
  console.log(url);
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Token peMPKUjADy9eMVxDg4SVMGFIsvfxlfcA5USlcc6M4aHewKaB4heJTK8kRu6uAkQ86xmh8UnQmEeyfcOTC7skGA==`,
    },
  });

  if (!response.ok) {
    logger.error("response:", response.ok);
    throw Error();
  }
  const jsonData = await response.json();
  const buckets = jsonData.buckets;

  const found = buckets.some((bucket: any) => {
    console.log("Bucket ID:", bucket.id);
    console.log("Name:", bucket.name);
    console.log("---------------------------");
    return bucket.name === _bucket;
  });
  console.log(found);
  return found;
}
