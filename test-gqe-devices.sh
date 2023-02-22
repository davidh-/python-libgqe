i=0
while [ $i -le 100 ]
do
	echo "Try: $i"
	echo "CPM:"
	./gqe-cli /dev/ttyUSB1 --unit GMC500Plus --revision 'Re 2.42'  --get-cpm
	echo "\nEMF:"
	./gqe-cli /dev/ttyUSB0 --unit GQEMF390 --revision 'Re 3.70'  --get-emf
	i=$(( $i + 1 ))
	echo "\n"
done
