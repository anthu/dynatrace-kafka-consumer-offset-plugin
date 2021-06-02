from ruxit.api.base_plugin import RemoteBasePlugin
from kafka import KafkaConsumer, TopicPartition
from struct import unpack_from
import threading
import logging

logger = logging.getLogger(__name__)

class KafkaOffsetPlugin(RemoteBasePlugin):

    def initialize(self, **kwargs):
        self.kafka = KafkaOffsetReader(self.config)

    def query(self, **kwargs):
      highwaters = self.kafka.get_highwater()
      offsets = self.kafka.get_offsets()

      # topic > group > partition

      for (topic, partition_offsets) in highwaters.items():
        group = self.topology_builder.create_group(identifier=topic, group_name=topic)

        highwaters = dict()
        for (partition, offset) in partition_offsets.items():
          highwaters[partition.partition] = offset
          group.absolute(key="topic.highwater", dimensions={"partition": str(partition)}, value=offset)

        
        if topic in offsets:
          for (consumer_group, group_offsets) in offsets[topic].items():
            device = group.create_device(identifier=str(consumer_group))

            for (partition, partition_offset) in group_offsets.items():
              if(partition in highwaters):
                lag = highwaters[partition] - partition_offset
                logger.debug("Lag calculated for " + topic + " - " + str(partition) + ": " + str(lag))
                device.absolute(key="consumer.lag", dimensions={"partition": str(partition)}, value=lag)

              device.absolute(key="consumer.offset", dimensions={"partition": str(partition)}, value=partition_offset)


def read_short(bytes):
    num = unpack_from('>h', bytes)[0]
    remaining = bytes[2:]
    return (num, remaining)

def read_int(bytes):
    num = unpack_from('>i', bytes)[0]
    remaining = bytes[4:]
    return (num, remaining)

def read_long_long(bytes):
    num = unpack_from('>q', bytes)[0]
    remaining = bytes[8:]
    return (num, remaining)

def read_string(bytes):
    length, remaining = read_short(bytes)
    string = remaining[:length].decode('utf-8')
    remaining = remaining[length:]
    return (string, remaining)

def parse_key(bytes):
    (version, remaining_key) = read_short(bytes)
    if version == 1 or version == 0:
        (group, remaining_key) = read_string(remaining_key)
        (topic, remaining_key) = read_string(remaining_key)
        (partition, remaining_key) = read_int(remaining_key)
        return (version, group, topic, partition)

def parse_value(bytes):
    (version, remaining_key) = read_short(bytes)
    if version == 0:
      (offset, remaining_key) = read_long_long(remaining_key)
      (metadata, remaining_key) = read_string(remaining_key)
      (timestamp, remaining_key) = read_long_long(remaining_key)
      return (version, offset, metadata, timestamp)
    elif version == 1:
      (offset, remaining_key) = read_long_long(remaining_key)
      (metadata, remaining_key) = read_string(remaining_key)
      (commit_timestamp, remaining_key) = read_long_long(remaining_key)
      (expire_timestamp, remaining_key) = read_long_long(remaining_key)
      return (version, offset, metadata, commit_timestamp, expire_timestamp)
    elif version == 3:
      (offset, remaining_key) = read_long_long(remaining_key)
      (leader_epoch, remaining_key) = read_int(remaining_key)
      (metadata, remaining_key) = read_string(remaining_key)
      (timestamp, remaining_key) = read_long_long(remaining_key)
      return (version, offset, leader_epoch, metadata, timestamp)

def ensure_dict_key(curr_dict, key, new_value):
    if key in curr_dict:
        return curr_dict

    new_dict = curr_dict.copy()
    new_dict[key] = new_value
    return new_dict

class KafkaOffsetReader():

  def run(self):
    while True:
      for message in self.consumer:
        exporter_partition = message.partition
        exporter_offset = message.offset

        self.exporter_offsets = ensure_dict_key(self.exporter_offsets, exporter_partition, exporter_offset)
        self.exporter_offsets[exporter_partition] = exporter_offset

        if message.key and message.value:
          key = parse_key(message.key)
          if key:
            value = parse_value(message.value)
            group = key[1]
            topic = key[2]
            partition = key[3]
            offset = value[1]

            self.topics.add(topic)

            self.offsets = ensure_dict_key(self.offsets, topic, {})
            self.offsets[topic] = ensure_dict_key(self.offsets[topic], group, {})
            self.offsets[topic][group] = ensure_dict_key(self.offsets[topic][group], partition, offset)
            self.offsets[topic][group][partition] = offset

            self.commits = ensure_dict_key(self.commits, topic, {})
            self.commits[topic] = ensure_dict_key(self.commits[topic], partition, {})
            self.commits[topic][partition] = ensure_dict_key(self.commits[topic][partition], group, 0)
            self.commits[topic][partition][group] += 1

  def __init__(self, config):
    logger.info("Config: %s", config)
    self.offsets = dict()
    self.commits = dict()
    self.exporter_offsets = dict()
    self.topics = set()
    self.bootstrap_servers = config["bootstrap_servers"]

    consumer_config = {
        'bootstrap_servers': config["bootstrap_servers"],
        'group_id': None,
        'auto_offset_reset': 'earliest',
        'consumer_timeout_ms': 500,
        'security_protocol': 'PLAINTEXT'
    }
  
    self.consumer = KafkaConsumer(
        '__consumer_offsets',
        **consumer_config
    )

    thread = threading.Thread(target=self.run, args=())
    thread.daemon = True                            # Daemonize thread
    thread.start()                                  # Start the execution

  def get_offsets(self):
    return self.offsets

  def get_highwater(self):
    if (len(self.topics) == 0):
      self.topics.add("heartbeat")
    topic_list = list(self.topics)
    con = KafkaConsumer(*topic_list, bootstrap_servers = self.bootstrap_servers)
    
    highwaters = dict()
    for topic in list(self.topics):
      ps = [TopicPartition(topic, p) for p in con.partitions_for_topic(topic)]
      highwaters[topic] = con.end_offsets(ps)
    
    con.close()

    return highwaters


# def test():
#   print("running")
#   kafka = KafkaOffsetReader({"bootstrap_servers": "localhost:9092"})
#   offsets = kafka.get_offsets()
#   highwaters = kafka.get_highwater()

# #   # topic > group > partition
#   for (topic, partition_offsets) in highwaters.items():
#     print("Creating Group: " + topic)
#     topic_highwaters = dict()
#     for (partition, offset) in partition_offsets.items():
#       topic_highwaters[partition.partition] = offset
#       print(topic_highwaters)
#       print("topic.highwater - " + topic + " - " + str(partition.partition) + " - " + str(offset))

#     if topic in offsets:
#       for (consumer_group, group_offsets) in offsets[topic].items():
#         print("Creating Device: " + consumer_group)
#         for (partition, partition_offset) in group_offsets.items():  
#           print(topic_highwaters[partition])
#           print("consumer.offset - " + topic + " - " + consumer_group + " - " + str(partition) + " - " + str(partition_offset))

# test()
