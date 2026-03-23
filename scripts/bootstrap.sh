#!/bin/bash
# TradeCraft Bootstrap Script
# One-command setup for the entire project

set -e

echo "🚀 TradeCraft Bootstrap"
echo "======================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check prerequisites
echo "📋 Checking prerequisites..."

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

# Check Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed. Please install Docker Compose first.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker and Docker Compose are installed${NC}"

# Setup environment
echo ""
echo "🔧 Setting up environment..."

if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${GREEN}✅ Created .env file from .env.example${NC}"
    echo -e "${YELLOW}⚠️  Please review and update the .env file with your settings${NC}"
else
    echo -e "${YELLOW}⚠️  .env file already exists, skipping${NC}"
fi

# Build and start services
echo ""
echo "🏗️  Building and starting services..."
docker-compose build

echo ""
echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to be ready
echo ""
echo "⏳ Waiting for services to be ready..."
sleep 10

# Run database migrations
echo ""
echo "🗄️  Running database migrations..."
docker-compose exec -T backend alembic upgrade head || echo "Migrations may need to be run manually"

# Seed sample data
echo ""
echo "🌱 Seeding sample data..."
docker-compose exec -T backend python scripts/seed_data.py || echo "Seed data may need to be run manually"

# Health check
echo ""
echo "🏥 Running health check..."
sleep 5

if curl -s http://localhost:8000/api/v1/admin/health > /dev/null; then
    echo -e "${GREEN}✅ Backend is healthy${NC}"
else
    echo -e "${YELLOW}⚠️  Backend health check failed, but services are starting${NC}"
fi

echo ""
echo "========================================"
echo -e "${GREEN}🎉 TradeCraft is ready!${NC}"
echo "========================================"
echo ""
echo "📱 Frontend: http://localhost:3000"
echo "🔌 Backend API: http://localhost:8000"
echo "📚 API Docs: http://localhost:8000/docs"
echo ""
echo "Useful commands:"
echo "  make logs     - View logs"
echo "  make down     - Stop services"
echo "  make test     - Run tests"
echo ""
