#!/bin/bash
# Get the current directory of this script,
# change directory to the project root path,
# create the folder that will contain the generated files
# read the file ".proto_sources.txt" that contains a list of .proto files
# iterate trough them and generate in ".generated" folder

path=$(readlink -f "${BASH_SOURCE:-$0}")
DIR_PATH=$(dirname $path)

echo "[proto] protobuffer compilation script"
echo "[proto] current directory" $DIR_PATH

cd $DIR_PATH/..
mkdir -p .generated

echo "[proto] compiling checked-in proto sources"
find external/serializers/proto -name '*.proto' -print | sort | while IFS= read -r line; do
  protoc -I. --python_out=.generated "$line"
  printf "\33[2K\r"
  printf "[proto] gen %s" "$line"
done
printf "\n"
echo "[proto] done generating"
