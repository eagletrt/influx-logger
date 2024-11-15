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
  const url = `${_url}/api/v2/buckets`;
  const Token =
    "peMPKUjADy9eMVxDg4SVMGFIsvfxlfcA5USlcc6M4aHewKaB4heJTK8kRu6uAkQ86xmh8UnQmEeyfcOTC7skGA==";
  console.log(url);
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Token ${Token}`,
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

export async function createNewBucket(_url: string, _bucketName: string) {
  const url = `${_url}/api/v2/buckets`;
  const Token =
    "peMPKUjADy9eMVxDg4SVMGFIsvfxlfcA5USlcc6M4aHewKaB4heJTK8kRu6uAkQ86xmh8UnQmEeyfcOTC7skGA==";
  const orgID = "7336e3e2d69a5216";
  const data = {
    name: _bucketName,
    description: _bucketName,
    orgID: orgID,
    retentionRules: [],
  };

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Token ${Token}`,
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      logger.error("response:", response.status);
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    logger.info("Bucket created:", _bucketName);
  } catch (error) {
    logger.error(error);
  }
}
