from elasticsearch import Elasticsearch, helpers
import json

class SubtitleDatabase:
    def __init__(self, host='elasticsearch', port=9200):
        self.es = Elasticsearch([{'host': host, 'port': port}])
        # Check if Elasticsearch is running
        if not self.es.ping():
            raise ValueError("Connection failed")
        
    def create_index(self, index_name):
        """Create a new index in Elasticsearch."""
        self.es.indices.create(index = index_name, ignore=400)
    
    def insert_subtitle(self, index_name, subtitle_doc):
        """
        Insert a subtitle into Elasticsearch.
        
        subtitle_doc should be a dict with the following structure:
        {
            'timestamp': '2021-01-01T00:00:00',
            'subtitle_text': 'Example subtitle text',
            'video_id': 'example_video_id'
        }
        """
        self.es.index(index=index_name, body=subtitle_doc)
    
    def bulk_insert(self, index_name, subtitle_docs):
        """
        Perform a bulk insert into Elasticsearch.
        
        subtitle_docs should be a list of subtitle_doc dicts.
        """
        actions = [
            {
                "_index": index_name,
                "_source": subtitle_doc
            }
            for subtitle_doc in subtitle_docs
        ]
        helpers.bulk(self.es, actions)
    
    # Additional methods (like search) can be added as needed
