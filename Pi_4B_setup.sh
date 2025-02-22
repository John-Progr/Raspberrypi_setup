#/bin/bash
###
# 3 input parameters
echo "Usage: $1: ADHOC_IP $2: CNTR_NET_ESSID $3: CNTR_NET_PWD"
##

###
# Preparation steps: 1. Copy client_control.sh script at Desktop and grant execute permission, 2. Connect ethernet cable to allow access to the Internet.
###

ETHER_NIC="eth0"
WNIC1="wlan0"
WNIC2="wlan1"

echo "1. Connect to the Internet through the ethernet cable"
sudo dhclient ${ETHER_NIC} -v

echo "2. Set-up the ad-hoc network at 5.2G through wlan0 (onboard NIC)"
sudo service networking stop
sudo killall wpa_supplicant

sudo echo "auto ${WNIC1}
iface ${WNIC1} inet static
    address 192.168.2.$1
    netmask 255.255.255.0
    wireless-channel 40
    wireless-essid myAdhoc
    wireless-mode ad-hoc" > /etc/network/interfaces
    
sudo ifdown ${WNIC1};
sudo ifup ${WNIC1};

iwconfig ${WNIC1};

echo "3. Set-up the control network at 2.4G through wlan1 (TPlink AC600)"
echo "3. a. getting driver"

sudo apt-get install dkms -y;
cd /tmp/
git clone https://github.com/aircrack-ng/rtl8812au.git
cd rtl8812au
make
sudo make install
sudo insmod 88XXau.ko

echo "3. b. connecting to the control network (using input parameters $2 and $3 as essid and password)"

sudo echo "allow-hotplug ${WNIC2};
iface wlan1 inet dhcp
wpa-conf /etc/wpa_supplicant.conf
iface default inet dhcp" >> /etc/network/interfaces

wpa_passphrase $2 $3 | sudo tee /etc/wpa_supplicant.conf

sudo ifdown $WNIC2;
sudo ifup $WNIC2;

iwconfig $WNIC2;

echo "4. update /etc/rc.local"
sudo sed -e 's/\<exit 0\>//g' /etc/rc.local | sudo tee /etc/rc.local

sudo echo "sudo service networking stop;
sudo ifup $WNIC1;
sudo ifup $WNIC2;
/home/pi/Desktop/./client_control.sh;
exit 0;" >> /etc/rc.local

echo "5. enable ssh"

sudo systemctl enable ssh
sudo systemctl start ssh
