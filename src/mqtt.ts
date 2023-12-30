import mqtt from 'mqtt'
import logger from './logger'
import { handleVersionMessage } from './handlers'

export async function estabilishMqttConnection(url: string, port: number = 1883): Promise<mqtt.MqttClient> {
  return mqtt.connectAsync(`mqtt:${url}`, {
    port: port,
    resubscribe: true,
    protocolId: 'MQTT',
    protocolVersion: 5,
  })
}

export async function handleIncomingMessage(topic: string, payload: Buffer) {
  logger.info(`Received incoming message on topic ${topic}`)
  for (const [ handlerTopic, handlerFunction ] of Object.entries(topicHandlers)) {
    if (buildTopicRegex(handlerTopic).test(topic)) {
      logger.info(`Topic has matched ${handlerTopic}`)
      handlerFunction(topic, payload)
    }
  }
}

export function buildTopicRegex(topic: string): RegExp {
  return new RegExp(topic.replace(/\//g, '\\/').replace(/\+/g, "([^\\/]+)").replace(/\#/g, ".*"), 'g')
}

export const topicHandlers = {
  '+/+/#': handleVersionMessage 
}
