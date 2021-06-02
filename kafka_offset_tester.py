from kafka_offset_reader import KafkaOffsetReader
import logging

logger = logging.getLogger(__name__)

def test():
  print("running")
  kafka = KafkaOffsetReader({"bootstrap_servers": "localhost:9092"})
  offsets = kafka.get_offsets()
  highwaters = kafka.get_highwater()

#   # topic > group > partition
  for (topic, partition_offsets) in highwaters.items():
    print("Creating Group: " + topic)
    topic_highwaters = dict()
    for (partition, offset) in partition_offsets.items():
      topic_highwaters[partition.partition] = offset
      print(topic_highwaters)
      print("topic.highwater - " + topic + " - " + str(partition.partition) + " - " + str(offset))

    if topic in offsets:
      for (consumer_group, group_offsets) in offsets[topic].items():
        print("Creating Device: " + consumer_group)
        for (partition, partition_offset) in group_offsets.items():  
          print(topic_highwaters[partition])
          print("consumer.offset - " + topic + " - " + consumer_group + " - " + str(partition) + " - " + str(partition_offset))

test()
