from source import TeleRagService
import asyncio

async def main():
    """
    Main function to start the TeleRagService.
    """
    service = TeleRagService()
    await service.start()
    await service.idle()

if __name__ == '__main__':
    asyncio.run(main())
