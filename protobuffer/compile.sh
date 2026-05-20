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

echo "[proto] reading proto sources list"
while IFS= read -r line; do
  protoc --python_out=.generated $line
  printf "\33[2K\r" # clear line
  printf "[proto] gen $line"
done < $DIR_PATH/.proto_sources.txt
printf "\n"
echo "[proto] done generating"
