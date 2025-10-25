# Setup Guide

Complete setup instructions for the Fund Performance Analysis System.

## Prerequisites

Before you begin, ensure you have the following installed:

- **Docker Desktop** (v20.10+)
- **Docker Compose** (v2.0+)
- **Git**
- **OpenAI API Key** (required for embeddings and LLM)

Optional (for local development without Docker):
- **Python 3.11+**
- **Node.js 18+**
- **PostgreSQL 15+**
- **Redis 7+**

---

## Quick Start (Recommended)

### 1. Clone the Repository

```bash
git clone <repository-url>
cd coding-test-3rd
```

### 2. Set Up Environment Variables

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your OpenAI API key
nano .env  # or use your preferred editor
```

**Required in `.env`:**
```bash
OPENAI_API_KEY=sk-your-actual-api-key-here
```

### 3. Start All Services

```bash
# Start all services (PostgreSQL, Redis, Backend, Frontend)
docker-compose up -d

# View logs
docker-compose logs -f
```

### 4. Initialize Database

The database will be automatically initialized on first run. To manually initialize:

```bash
docker-compose exec backend python app/db/init_db.py
```

### 5. Access the Application

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5432 (user: funduser, password: fundpass, db: funddb)
- **Redis**: localhost:6379

### 6. Upload Sample Document

1. Navigate to http://localhost:3000/upload
2. Upload the sample PDF: `files/ILPA based Capital Accounting and Performance Metrics_ PIC, Net PIC, DPI, IRR  .pdf`
3. Wait for processing to complete (~1-2 minutes)
4. Go to http://localhost:3000/chat and start asking questions!

---

## Local Development Setup (Without Docker)

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your settings

# Start PostgreSQL and Redis locally
# (Install via Homebrew on Mac, apt on Linux, or download for Windows)

# Initialize database
python -m app.db.init_db

# Run development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Set up environment variables
cp .env.example .env.local
# Edit .env.local if needed

# Run development server
npm run dev
```

---

## Configuration

### Backend Configuration

Edit `backend/.env`:

```bash
# Database
DATABASE_URL=postgresql://funduser:fundpass@localhost:5432/funddb

# Redis
REDIS_URL=redis://localhost:6379/0

# OpenAI (Required)
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_MODEL=gpt-4-turbo-preview
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# File Upload
UPLOAD_DIR=/app/uploads
MAX_UPLOAD_SIZE=52428800  # 50MB

# Vector Store
VECTOR_STORE_PATH=/app/vector_store
FAISS_INDEX_PATH=/app/faiss_index

# Document Processing
CHUNK_SIZE=1000
CHUNK_OVERLAP=200

# RAG
TOP_K_RESULTS=5
SIMILARITY_THRESHOLD=0.7
```

### Frontend Configuration

Edit `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Troubleshooting

### Issue: Docker containers won't start

**Solution:**
```bash
# Stop all containers
docker-compose down

# Remove volumes (WARNING: This deletes all data)
docker-compose down -v

# Rebuild and start
docker-compose up --build
```

### Issue: Backend can't connect to PostgreSQL

**Solution:**
```bash
# Check if PostgreSQL is running
docker-compose ps

# Check PostgreSQL logs
docker-compose logs postgres

# Restart PostgreSQL
docker-compose restart postgres
```

### Issue: "OpenAI API key not found" error

**Solution:**
1. Ensure `.env` file exists in the root directory
2. Verify `OPENAI_API_KEY` is set correctly
3. Restart backend: `docker-compose restart backend`

### Issue: Frontend can't connect to backend

**Solution:**
1. Check backend is running: http://localhost:8000/health
2. Verify `NEXT_PUBLIC_API_URL` in frontend `.env.local`
3. Check CORS settings in `backend/app/main.py`

### Issue: Document parsing fails

**Solution:**
1. Check backend logs: `docker-compose logs backend`
2. Verify PDF is not corrupted or password-protected
3. Ensure file size is under 50MB
4. Check Docling installation: `docker-compose exec backend pip show docling`

### Issue: Vector search returns no results

**Solution:**
1. Verify documents were processed successfully
2. Check FAISS index exists: `docker-compose exec backend ls -la /app/faiss_index/`
3. Verify embeddings are being generated (check logs)
4. Try lowering `SIMILARITY_THRESHOLD` in config

### Issue: Out of memory errors

**Solution:**
```bash
# Increase Docker memory limit (Docker Desktop > Settings > Resources)
# Recommended: 4GB+ RAM

# Or reduce batch sizes in backend/app/core/config.py
CHUNK_SIZE=500  # Reduce from 1000
```

---

## Database Management

### Connect to PostgreSQL

```bash
# Using Docker
docker-compose exec postgres psql -U funduser -d funddb

# Using local psql
psql -h localhost -U funduser -d funddb
```

### View Tables

```sql
\dt  -- List all tables
SELECT * FROM funds;
SELECT * FROM capital_calls LIMIT 10;
SELECT * FROM distributions LIMIT 10;
```

### Reset Database

```bash
# Stop containers
docker-compose down

# Remove database volume
docker volume rm coding-test-3rd_postgres_data

# Restart
docker-compose up -d
```

---

## Testing

### Backend Tests

```bash
cd backend

# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/test_metrics.py -v
```

### Frontend Tests

```bash
cd frontend

# Run tests
npm test

# Run with coverage
npm test -- --coverage
```

### API Testing with cURL

```bash
# Health check
curl http://localhost:8000/health

# Upload document
curl -X POST "http://localhost:8000/api/documents/upload" \
  -F "file=@files/sample.pdf"

# Query chat
curl -X POST "http://localhost:8000/api/chat/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the current DPI?", "fund_id": 1}'

# Get fund metrics
curl http://localhost:8000/api/funds/1/metrics
```

---

## Production Deployment

### Environment Variables for Production

```bash
# Use strong passwords
DATABASE_URL=postgresql://user:strong_password@db_host:5432/funddb

# Use production Redis
REDIS_URL=redis://redis_host:6379/0

# Enable HTTPS
ALLOWED_ORIGINS=["https://yourdomain.com"]

# Use production API keys
OPENAI_API_KEY=sk-production-key

# Configure file storage (S3, etc.)
UPLOAD_DIR=/var/app/uploads
```

### Build for Production

```bash
# Backend
cd backend
docker build -t fund-backend:latest .

# Frontend
cd frontend
npm run build
docker build -t fund-frontend:latest .
```

### Deploy to Cloud

**AWS Example:**
```bash
# Push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com
docker tag fund-backend:latest <account>.dkr.ecr.us-east-1.amazonaws.com/fund-backend:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/fund-backend:latest

# Deploy to ECS/EKS
# (Use your preferred deployment method)
```

---

## Monitoring

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend

# Last 100 lines
docker-compose logs --tail=100 backend
```

### Check Service Health

```bash
# Backend health
curl http://localhost:8000/health

# PostgreSQL
docker-compose exec postgres pg_isready

# Redis
docker-compose exec redis redis-cli ping
```

### Monitor Resource Usage

```bash
# Docker stats
docker stats

# Disk usage
docker system df
```

---

## Backup and Restore

### Backup Database

```bash
# Backup to file
docker-compose exec postgres pg_dump -U funduser funddb > backup.sql

# Backup with Docker
docker-compose exec -T postgres pg_dump -U funduser funddb | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Restore Database

```bash
# Restore from file
docker-compose exec -T postgres psql -U funduser funddb < backup.sql

# Restore from gzipped file
gunzip < backup.sql.gz | docker-compose exec -T postgres psql -U funduser funddb
```

### Backup Vector Store

```bash
# Copy FAISS index
docker cp fund-backend:/app/faiss_index ./faiss_backup

# Restore
docker cp ./faiss_backup fund-backend:/app/faiss_index
```

---

## Updating

### Update Dependencies

```bash
# Backend
cd backend
pip install --upgrade -r requirements.txt

# Frontend
cd frontend
npm update
```

### Update Docker Images

```bash
# Pull latest base images
docker-compose pull

# Rebuild
docker-compose up --build
```

---

## Uninstall

```bash
# Stop and remove containers
docker-compose down

# Remove volumes (deletes all data)
docker-compose down -v

# Remove images
docker rmi coding-test-3rd_backend coding-test-3rd_frontend

# Remove project directory
cd ..
rm -rf coding-test-3rd
```

---

## Getting Help

- **Documentation**: See `docs/` directory
- **API Docs**: http://localhost:8000/docs
- **Issues**: Open an issue on GitHub
- **Logs**: Check `docker-compose logs` for errors

---

## Next Steps

1. ✅ Complete setup
2. 📄 Upload a fund document
3. 💬 Try the chat interface
4. 📊 Explore fund metrics
5. 🔧 Customize for your needs

**Happy analyzing! 🚀**
