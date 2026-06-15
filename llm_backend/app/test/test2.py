import asyncio

from ollama_benchmark import OllamaBenchmark


async def main():
    benchmark = OllamaBenchmark(
        url="http://localhost:11434",
        model="llama3:latest",
    )

    # 可选：先确保模型可用
    if not await benchmark.ensure_model_available():
        print("模型准备失败，退出测试")
        return

    # 调用 find_max_concurrency 方法
    result = await benchmark.find_max_concurrency(
        start_concurrent=20,
        max_concurrent=30,
        requests_per_test=10,
        success_rate_threshold=0.95,
        latency_threshold=5.0,
    )

    print("最大并发测试结果：")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())