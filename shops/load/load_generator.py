
import asyncio
import random
import time
import argparse
import statistics
from collections import Counter

import httpx


SHOPS = {
    "Pinecart": {
        "url": "http://127.0.0.1:8001",
        "history": "/customers/{id}/orders",
        "cart": "/cart/items",
        "order": "/orders/{id}",
        "cart_id": "customer_id",
    },
    "Tealbox": {
        "url": "http://127.0.0.1:8002",
        "history": "/buyers/{id}/purchases",
        "cart": "/basket/items",
        "order": "/purchases/{id}",
        "cart_id": "buyer_id",
    },
}


def percentile(values, p):
    if not values:
        return 0
    values = sorted(values)
    index = min(int(len(values) * p), len(values) - 1)
    return values[index]


async def send_request(client, method, url, **kwargs):
    start = time.perf_counter()

    try:
        response = await client.request(method, url, **kwargs)
        latency = (time.perf_counter() - start) * 1000
        return latency, response.status_code

    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        print(f"Request failed: {exc}")
        return latency, 0


async def simulate_shop(name, config, rps, duration):
    results = []
    statuses = Counter()

    total_requests = rps * duration
    interval = 1 / rps

    async with httpx.AsyncClient(timeout=10) as client:

        async def perform_request():
            customer_id = random.randint(1, 100)
            product_id = random.randint(1, 20)

            # Traffic distribution
            action = random.choices(
                ["browse", "detail", "history", "cart", "order"],
                weights=[55, 15, 20, 7, 3]
            )[0]

            base = config["url"]

            if action == "browse":
                method = "GET"
                path = "/products?page=1"

                latency, status = await send_request(
                    client, method, base + path
                )

            elif action == "detail":
                path = f"/products/{product_id}"

                latency, status = await send_request(
                    client, "GET", base + path
                )

            elif action == "history":
                path = config["history"].format(id=customer_id)

                latency, status = await send_request(
                    client, "GET", base + path
                )

            elif action == "cart":
                payload = {
                    config["cart_id"]: customer_id,
                    "product_id": product_id,
                    "quantity": 1,
                }

                latency, status = await send_request(
                    client, "POST", base + config["cart"],
                    json=payload
                )

            else:
                # Add an item first so the cart is not empty.
                payload = {
                    config["cart_id"]: customer_id,
                    "product_id": product_id,
                    "quantity": 1,
                }

                await send_request(
                    client, "POST", base + config["cart"],
                    json=payload
                )

                path = config["order"].format(id=customer_id)

                latency, status = await send_request(
                    client, "POST", base + path
                )

            results.append(latency)
            statuses[status] += 1

        tasks = []
        start = time.perf_counter()

        for i in range(total_requests):
            target_time = start + i * interval
            delay = target_time - time.perf_counter()

            if delay > 0:
                await asyncio.sleep(delay)

            tasks.append(asyncio.create_task(perform_request()))

        await asyncio.gather(*tasks)

    successful = sum(
        count for status, count in statuses.items()
        if 200 <= status < 300
    )

    print(f"\n{'=' * 45}")
    print(f"{name} LOAD TEST RESULTS")
    print(f"{'=' * 45}")
    print(f"Requests:       {len(results)}")
    print(f"Successful:     {successful}")
    print(f"Errors:         {len(results) - successful}")
    print(f"Average:        {statistics.mean(results):.2f} ms")
    print(f"p50:            {percentile(results, 0.50):.2f} ms")
    print(f"p95:            {percentile(results, 0.95):.2f} ms")
    print(f"p99:            {percentile(results, 0.99):.2f} ms")
    print(f"HTTP statuses:  {dict(statuses)}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rps", type=int, default=20)
    parser.add_argument("--duration", type=int, default=30)
    args = parser.parse_args()

    if args.rps < 1 or args.duration < 1:
        parser.error("--rps and --duration must be positive")

    print("Starting load test...")
    print(f"Rate: {args.rps} requests/second per shop")
    print(f"Duration: {args.duration} seconds per shop")

    await asyncio.gather(
        *[
            simulate_shop(name, config, args.rps, args.duration)
            for name, config in SHOPS.items()
        ]
    )


if __name__ == "__main__":
    asyncio.run(main())
