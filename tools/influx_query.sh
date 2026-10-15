TOKEN=token
URL=http://localhost:8086
MEASUREMENT=measurement
FIELD=motortemperature
TIME=-20m
DIR=debug_logs

mkdir -p $DIR
curl --request POST \
  "$URL/api/v2/query?org=eagletrt" \
  --header "Authorization: Token $TOKEN" \
  --header "Accept: application/csv" \
  --header "Content-type: application/vnd.flux" \
  --data-binary "
from(bucket: \"telemetry_adr\")
  |> range(start: $TIME)
  |> filter(fn: (r) => r[\"_measurement\"] == \"$MEASUREMENT\")
  |> filter(fn: (r) => r[\"_field\"] == \"$FIELD\")
" \
  -o "$DIR"/"$MEASUREMENT"_"$FIELD".csv
