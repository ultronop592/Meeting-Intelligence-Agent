import asyncio
import logging 
import os 
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from numpy import select
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from Backend.core.config import settings
 
