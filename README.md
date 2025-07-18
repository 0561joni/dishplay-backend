# DishPlay Backend API

A robust FastAPI backend for the DishPlay menu digitization application.

## Features

- **Menu Processing**: Upload menu images and extract items using GPT-4 Vision
- **Image Search**: Automatically find food images for each menu item using Google Custom Search
- **Authentication**: JWT-based authentication with Supabase
- **Credit System**: Track and manage user credits for menu uploads
- **Logging**: Comprehensive logging for debugging and monitoring

## Tech Stack

- **Framework**: FastAPI
- **Database**: Supabase (PostgreSQL)
- **Authentication**: Supabase Auth with JWT validation
- **AI**: OpenAI GPT-4 Vision for menu extraction
- **Image Search**: Google Custom Search API
- **Image Processing**: Pillow for optimization

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── auth.py           # JWT validation and user authentication
│   │   ├── logging.py        # Logging configuration
│   │   └── supabase_client.py # Supabase client initialization
│   ├── models/
│   │   ├── __init__.py
│   │   ├── menu.py          # Menu-related Pydantic models
│   │   └── user.py          # User-related Pydantic models
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py          # Authentication endpoints
│   │   ├── menu.py          # Menu upload and retrieval endpoints
│   │   └── user.py          # User profile endpoints
│   └── services/
│       ├── __init__.py
│       ├── google_search_service.py  # Google Custom Search integration
│       ├── image_processor.py        # Image optimization
│       └── openai_service.py         # OpenAI GPT-4 Vision integration
├── main.py                   # FastAPI application entry point
├── requirements.txt          # Python dependencies
├── Dockerfile               # Docker configuration
├── render.yaml              # Render.com deployment configuration
└── .env.example             # Environment variables template
```

## Setup

1. **Clone the repository**

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your actual values
   ```

5. **Run the application**:
   ```bash
   python main.py
   ```

## API Endpoints

### Health Check
- `GET /` - API root
- `GET /health` - Health check with database status

### Authentication
- `GET /api/auth/health` - Auth service health check

### Menu Endpoints
- `POST /api/menu/upload` - Upload and process a menu image
- `GET /api/menu/{menu_id}` - Get a specific menu with items
- `GET /api/menu/user/all` - Get all menus for the current user

### User Endpoints
- `GET /api/user/profile` - Get current user profile
- `PUT /api/user/profile` - Update user profile
- `GET /api/user/credits` - Get user credit balance

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anonymous key |
| `SUPABASE_JWT_SECRET` | Supabase JWT secret (optional, defaults to anon key) |
| `OPENAI_API_KEY` | OpenAI API key for GPT-4 Vision |
| `GOOGLE_CSE_API_KEY` | Google Custom Search API key |
| `GOOGLE_CSE_ID` | Google Custom Search Engine ID |
| `ENVIRONMENT` | Environment (development/production) |
| `PORT` | Server port (default: 8000) |

## Deployment on Render

1. Push your code to GitHub
2. Connect your GitHub repository to Render
3. Use the provided `render.yaml` for automatic configuration
4. Set all environment variables in Render dashboard
5. Deploy!

## API Documentation

Once running, access the interactive API documentation at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Error Handling

The API implements comprehensive error handling:
- 400: Bad Request (invalid input)
- 401: Unauthorized (invalid/missing token)
- 402: Payment Required (insufficient credits)
- 404: Not Found
- 422: Unprocessable Entity (processing errors)
- 500: Internal Server Error

## Logging

The application uses Python's logging module with:
- Structured logging format
- Different log levels for different modules
- Console output for easy debugging

## Security

- JWT token validation for all protected endpoints
- Input validation using Pydantic models
- Image size limits (10MB)
- Secure error messages (no sensitive data exposed)
