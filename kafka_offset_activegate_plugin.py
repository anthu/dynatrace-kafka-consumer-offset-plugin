from ruxit.api.base_plugin import RemoteBasePlugin
import logging
from kafka_offset_reader import KafkaOffsetReader

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

