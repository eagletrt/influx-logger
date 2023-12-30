import mqtt from 'mqtt'

export async function estabilishMqttConnection(url: string, port: number = 1883): Promise<mqtt.MqttClient> {
  return mqtt.connectAsync(`mqtt:${url}`, {
    port: port,
    resubscribe: true,
    protocolId: 'MQTT',
    protocolVersion: 5,
  })
}


