#!/bin/sh

: ${SLEEP_LENGTH:=2}

wait_for() {
  stdbuf -i0 -o0 -e0 echo -n "Waiting for $1 to listen on $2..."
  while ! nc -z $1 $2; do stdbuf -i0 -o0 -e0 echo -n '.'; sleep $SLEEP_LENGTH; done
  echo ""
}

for var in "$@"
do
  host=${var%:*}
  port=${var#*:}
  wait_for $host $port
done
