#!/usr/bin/env bash

hash curl 2>/dev/null || { echo >&2 "I require curl but it's not installed.  Aborting."; exit 1; }
hash jq 2>/dev/null || { echo >&2 "I require jq (https://stedolan.github.io/jq) but it's not installed.  Aborting."; exit 1; }

failures=0

echo
echo Testing Create
echo

r=`curl -s http://localhost:8888/api/posts/ -w "\n%{http_code}" --header "Content-Type: application/vnd.api+json" --data '{"data": {"type": "post", "attributes": {"author": "Andrew", "text": "RAWR"}}}'`
echo $r
code=`echo "$r" | tail -n1`
if [ "$code" -ne "201" ]; then
	((failures++))
	echo FAILED
fi

echo
echo Testing Read
echo

id=`curl -s http://localhost:8888/api/posts/ --header "Content-Type: application/vnd.api+json" --data '{"data": {"type": "post", "attributes": {"author": "Andrew", "text": "YAY"}}}'| jq -r '.data.id' 2> /dev/null`
r=`curl -s http://localhost:8888/api/posts/$id -w "\n%{http_code}" --header "Content-Type: application/vnd.api+json"`
echo $r
code=`echo "$r" | tail -n1`
if [ "$code" -ne "200" ]; then
	((failures++))
	echo FAILED
fi

echo
echo Testing Update
echo

text="POOPOO"
r=`curl -s http://localhost:8888/api/posts/$id -w "\n%{http_code}" --header "Content-Type: application/vnd.api+json" --data '{"data": {"type": "post", "id": "'$id'", "attributes": {"text": "'$text'"}}}' -X PATCH`
echo $r
code=`echo "$r" | tail -n1`
if [ "$code" -ne "200" ]; then
	((failures++))
	echo FAILED
fi
newtext=`echo $r | jq -r '.data.attributes.text' 2> /dev/null`
if [ "$newtext" != "$text" ]; then
	((failures++))
	echo FAILED
fi


echo
echo Testing Delete
echo

id=`curl -s http://localhost:8888/api/posts/ --header "Content-Type: application/vnd.api+json" --data '{"data": {"type": "post", "attributes": {"author": "Andrew", "text": "QQ"}}}'| jq -r '.data.id' 2> /dev/null`
r=`curl -s http://localhost:8888/api/posts/$id -w "\n%{http_code}" --header "Content-Type: application/vnd.api+json" -X DELETE`
echo $r
code=`echo "$r" | tail -n1`
if [ "$code" -ne "204" ]; then
	((failures++))
	echo FAILED
fi
data=`curl -s http://localhost:8888/api/posts/$id --header "Content-Type: application/vnd.api+json" | jq -r '.data' 2> /dev/null`
echo $data
if [ "$data" != "null" ]; then
	((failures++))
	echo FAILED
fi

echo
echo Testing List
echo

r=`curl -s http://localhost:8888/api/posts/ -w "\n%{http_code}" --header "Content-Type: application/vnd.api+json"`
echo $r
code=`echo "$r" | tail -n1`
if [ "$code" -ne "200" ]; then
	((failures++))
	echo FAILED
fi


echo
if [ "$failures" -ne "0" ]; then
	echo -e "\e[31mThere were $failures FAILURES!\e[0m"
else
	echo -e "\e[32mAll tests passed.\e[0m"
fi
