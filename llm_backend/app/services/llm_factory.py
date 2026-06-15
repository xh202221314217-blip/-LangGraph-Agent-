from app.services.deepseek_service import DeepseekService
from app.services.search_service import SearchService
class LLMFactory:
    @staticmethod
    def create_chat_service():
        """创建聊天服务实例，固定使用 DeepSeek API。"""
        return DeepseekService(use_cache=False)

    @staticmethod
    def create_reasoner_service():
        """创建推理服务实例，固定使用 DeepSeek API。"""
        return DeepseekService(use_cache=False)
    
    @staticmethod
    def create_search_service():
        """创建搜索服务实例"""
        return SearchService()
