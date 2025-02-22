import logging
import ssl 
import json 
import time 
import subprocess 
import paho.mqtt.client as mqtt 
from datetime import datetime, timedelta

from olsr_jsoninfo import JsonInfo, Neighbor

#Those fields must be configured by developer in order for script to start sending
class HonoMqttDevice:
    DEVICE_AUTH_ID = ""
    DEVICE_PASSWORD = ""
    DEVICE_NAME = ""
    MQTT_BROKER_HOST = ""
    MQTT_BROKER_PORT = 8883  # Secure MQTT port
    TENANT_ID = ""
    CA_FILE_PATH = "/tmp/c2e_hono_truststore.pem"

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)

        self.client = mqtt.Client(client_id=self.DEVICE_AUTH_ID, clean_session=False)
        self.client.username_pw_set(
            username=f"{self.DEVICE_AUTH_ID}@{self.TENANT_ID}",
            password=self.DEVICE_PASSWORD
        )

        try:
            self.client.tls_set(
                ca_certs=self.CA_FILE_PATH,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS
            )
            self.client.tls_insecure_set(True)
        except Exception as e:
            self.logger.error(f"TLS setup failed: {e}")
            raise

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        self.jsoninfo = JsonInfo()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.logger.info("Successfully connected to MQTT broker")
            self.client.subscribe(f"command/{self.TENANT_ID}//req/#")
        else:
            self.logger.error(f"Connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.logger.warning(f"Disconnected with code {rc}")

    def _on_message(self, client, userdata, msg):
        try:
            self.logger.info(f"Received message on {msg.topic}: {msg.payload.decode()}")
            payload = json.loads(msg.payload)
            value = payload.get('value', {})
            hl_int = value.get("hl_int")
            tc_int = value.get("tc_int")
            print("hl_int: ", hl_int)
            print("tc_int: ", tc_int)
            if hl_int and tc_int:
                self.update_olsr_config(hl_int, tc_int)
                self.restart_olsrd()
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")

    @staticmethod
    def wait_until_next_time(target_hour, target_minute):
        now = datetime.now()
        target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        if now > target_time:
            target_time += timedelta(days=1)

        time_to_wait = (target_time - now).total_seconds()
        print(f"Waiting until {target_time} to start the script...")
        time.sleep(time_to_wait)
        print(f"Starting the script at {target_time}.")

    def check_olsrd_errors(self):
        try:
            command = "sudo journalctl -u olsrd.service | grep -iE 'failed|error|failure'"
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            logs = result.stdout.strip()
            return 1 if logs else 0
        except Exception as e:
            self.logger.error(f"Error checking OLSRd logs: {e}")
            return 1

    def get_neighbors(self):
        try:
            neighbors = self.jsoninfo.neighbors()
            return [{"ipv4Address": neighbor.ipv4Address} for neighbor in neighbors]
        except Exception as e:
            self.logger.error(f"Error fetching neighbors: {e}")
            return []

    def get_device_ip(self):
        try:
            # Get the IP address of the device on the wlan0 interface
            command = "hostname -I | awk '{print $1}'"
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            device_ip = result.stdout.strip()
            if device_ip:
                return device_ip
            else:
                self.logger.error("No IP address found for wlan0")
                return "0.0.0.0"
        except Exception as e:
            self.logger.error(f"Error fetching device IP: {e}")
            return "0.0.0.0"

    def send_telemetry(self):
        topic = "telemetry"
        neighbors = self.get_neighbors()
        error_status = self.check_olsrd_errors()

        # Get the device's IP address
        device_ip = self.get_device_ip()

        config_path = "/etc/olsrd/olsrd.conf"
        hl_int, tc_int = None, None

        try:
            with open(config_path, "r") as file:
                for line in file:
                    line = line.strip()
                    if line.startswith("HelloInterval"):
                        hl_int = float(line.split()[1])
                    elif line.startswith("TcInterval"):
                        tc_int = float(line.split()[1])
        except Exception as e:
            self.logger.error(f"Error reading OLSR config: {e}")

        payload = {
            "topic": f"org.acme/{self.DEVICE_NAME}/things/twin/commands/modify",
            "headers": {},
            "path": "/features/network/properties",
            "value": {
                "device_ip": device_ip,  # Add device_ip field
                "neighbors": neighbors,
                "hl_int": hl_int,
                "tc_int": tc_int,
                "error": error_status,
            }
        }

        self.client.publish(topic, json.dumps(payload))
        self.logger.info(f"Published telemetry to {topic}: {json.dumps(payload)}")

    def update_olsr_config(self, hl_int, tc_int):
        try:
            config_path = "/etc/olsrd/olsrd.conf"
            with open(config_path, "r") as file:
                lines = file.readlines()

            with open(config_path, "w") as file:
                for line in lines:
                    stripped_line = line.strip()  # Strip only the unnecessary spaces at the beginning or end
                    if stripped_line.startswith("HelloInterval"):
                       file.write(f"{line[:line.find('HelloInterval')]}HelloInterval {hl_int}\n")  # Ensure we maintain the format before the value
                    elif stripped_line.startswith("TcInterval"):
                       file.write(f"{line[:line.find('TcInterval')]}TcInterval {tc_int}\n")
                    else:
                       file.write(line)  # Keep other lines exactly as they are
            self.logger.info(f"Updated {config_path} with HelloInterval={hl_int}, TcInterval={tc_int}")
        except Exception as e:
            self.logger.error(f"Error updating OLSR config: {e}")
            raise

    def restart_olsrd(self):
        try:
            self.logger.info("Stopping OLSRd process...")
            subprocess.run(["sudo", "pkill", "-f", "olsrd"], check=False)
            self.logger.info("Starting OLSRd process normally with -i wlan0...")
            time.sleep(1)
            subprocess.run(["sudo", "olsrd", "-i", "wlan0"], check=True)
            
            self.logger.info("OLSRd process restarted successfully.")
            self.logger.info("5 seconds delay to start next cycle.")
            time.sleep(5)
            self.logger.info("Next Cyle Begins.")
            
        except Exception as e:
            self.logger.error(f"Error restarting OLSRd process: {e}")
            raise

    def connect(self):
       try:
           self.client.connect(self.MQTT_BROKER_HOST, self.MQTT_BROKER_PORT, 120)
           self.client.loop_start()  # Keeps the connection alive
           self.logger.info("Successfully connected to MQTT broker — Ready to receive commands.")
       except Exception as e:
           self.logger.error(f"Connection error: {e}")
           raise

    def run(self):
       try:
           self.send_telemetry()  # Send telemetry without disconnecting
           time.sleep(2)
       except Exception as e:
           self.logger.error(f"Error in run: {e}")


def main():
   # HonoMqttDevice.wait_until_next_time(20, 48)
    time.sleep(1)
    device = HonoMqttDevice()
    device.connect()

    while True:
        try:
            device.run()
            time.sleep(30)
        except KeyboardInterrupt:
            print("\nExecution interrupted by user. Exiting...")
            print("Cleaning up resources...")
            device.client.loop_stop()
            device.client.disconnect()
            print("MQTT client disconnected")
            break
        except Exception as e:
            print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
