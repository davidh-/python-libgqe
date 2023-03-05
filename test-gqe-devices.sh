# debugging usb hub adapater 2/21/23
i=0
while [ $i -le 100000 ]
do
	echo "Try: $i"
	echo -n "CPM: "
	./gqe-cli /dev/ttyUSB1 --unit GMC500Plus --revision 'Re 2.42'  --get-cpm
	echo ""
	echo -n "EMF: "
	./gqe-cli /dev/ttyUSB0 --unit GQEMF390 --revision 'Re 3.70'  --get-emf
	i=$(( $i + 1 ))
	echo ""
	sleep 1
done

#from usb.core import find as finddev
#dev = finddev(idVendor=0x1a40, idProduct=0x0101)
#dev.reset()
