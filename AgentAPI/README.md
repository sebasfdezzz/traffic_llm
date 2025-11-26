# AMG Traffic Data Assistant 🚦

A web-based natural language interface for querying AMG traffic data stored in Aurora PostgreSQL. This application uses LangChain and OpenAI to translate natural language questions into SQL queries and provides reverse geocoding to convert coordinates into street addresses.

## Features

- 🗣️ **Natural Language Queries**: Ask questions about traffic data in plain language
- 🗺️ **Reverse Geocoding**: Automatically converts coordinates to street names and areas
- 🎨 **Modern UI**: Clean, responsive chat-like interface
- 🔍 **Intelligent SQL Agent**: Uses LangChain to understand and query the database
- 🚀 **Production Ready**: Configured for EC2 deployment with Gunicorn

## Prerequisites

- Python 3.8 or higher
- AWS Aurora PostgreSQL database with traffic data
- OpenAI API key
- EC2 instance (for deployment)

## Project Structure

```
AgentAPI/
├── app.py                 # Main Flask application
├── templates/
│   └── index.html        # Web UI template
├── static/
│   └── style.css         # UI styling
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables (create from .env.example)
├── .env.example          # Example environment configuration
└── README.md             # This file
```

## Local Development Setup

### 1. Clone and Navigate to Project

```bash
cd AgentAPI
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the `AgentAPI` directory:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Aurora PostgreSQL Configuration
AURORA_HOST=amg-traffic-cluster.cluster-clss68yoix1c.us-east-2.rds.amazonaws.com
AURORA_DB=postgres
DB_USER=root
DB_PASS=your_password_here
DB_PORT=5432

# OpenAI Configuration
OPENAI_API_KEY=sk-your-openai-api-key-here
```

### 5. Run Development Server

```bash
python app.py
```

Visit `http://localhost:5000` in your browser.

## EC2 Deployment

### 1. Launch EC2 Instance

- **AMI**: Amazon Linux 2023 or Ubuntu 22.04
- **Instance Type**: t3.small or larger (recommended)
- **Security Group**: 
  - Allow SSH (port 22) from your IP
  - Allow HTTP (port 80) from anywhere (0.0.0.0/0)
  - Allow HTTPS (port 443) from anywhere (optional, for SSL)
  - Allow Custom TCP (port 5000) from anywhere (for testing)

### 2. Connect to EC2 Instance

```bash
ssh -i your-key.pem ec2-user@your-ec2-public-ip
```

### 3. Install System Dependencies

**For Amazon Linux 2023:**
```bash
sudo yum update -y
sudo yum install python3.11 python3-pip git -y
```

**For Ubuntu:**
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git -y
```

### 4. Transfer Files to EC2

From your local machine:

```bash
scp -i your-key.pem -r AgentAPI ec2-user@your-ec2-public-ip:~/
```

Or clone from Git repository if you have one.

### 5. Setup Application on EC2

```bash
cd ~/AgentAPI

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
nano .env
# (Paste your environment variables and save)
```

### 6. Run with Gunicorn (Production)

**Test Gunicorn:**
```bash
gunicorn --bind 0.0.0.0:5000 app:app
```

**Create systemd service for auto-start:**

```bash
sudo nano /etc/systemd/system/traffic-assistant.service
```

Add the following content:

```ini
[Unit]
Description=AMG Traffic Data Assistant
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/AgentAPI
Environment="PATH=/home/ec2-user/AgentAPI/venv/bin"
ExecStart=/home/ec2-user/AgentAPI/venv/bin/gunicorn --workers 3 --bind 0.0.0.0:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

**Enable and start the service:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable traffic-assistant
sudo systemctl start traffic-assistant
sudo systemctl status traffic-assistant
```

### 7. Setup Nginx as Reverse Proxy (Optional but Recommended)

```bash
# Install Nginx
sudo yum install nginx -y  # Amazon Linux
# or
sudo apt install nginx -y  # Ubuntu

# Configure Nginx
sudo nano /etc/nginx/conf.d/traffic-assistant.conf
```

Add the following configuration:

```nginx
server {
    listen 80;
    server_name your-domain.com;  # or EC2 public IP

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Start Nginx:**

```bash
sudo systemctl enable nginx
sudo systemctl start nginx
```

Now your application will be accessible at `http://your-ec2-public-ip/`

## Database Schema

The application expects a `traffic_data` table with the following structure:

```sql
CREATE TABLE traffic_data (
    id TEXT,
    predominant_color TEXT,
    exponential_color_weighting FLOAT,
    linear_color_weighting FLOAT,
    diffuse_logic_traffic FLOAT,
    coordx FLOAT,  -- Latitude
    coordy FLOAT   -- Longitude
);
```

## Example Questions

Try asking questions like:

- "What is the average exponential color weighting for red traffic areas?"
- "Show me the top 10 locations with the highest traffic scores"
- "How many records have green predominant color?"
- "What are the coordinates of areas with the worst traffic?"
- "Give me traffic data for locations near latitude 25.6866"

## API Endpoints

- `GET /` - Web UI
- `POST /ask` - Submit a question
  ```json
  {
    "question": "Your question here"
  }
  ```
- `GET /health` - Health check endpoint
- `GET /table-info` - Get database table information

## Troubleshooting

### Database Connection Issues

1. Check Aurora security group allows connections from EC2
2. Verify credentials in `.env` file
3. Test connection: `psql -h AURORA_HOST -U DB_USER -d AURORA_DB`

### OpenAI API Issues

1. Verify API key is valid
2. Check OpenAI account has credits
3. Review rate limits

### Application Not Starting

```bash
# Check logs
sudo journalctl -u traffic-assistant -n 50 -f

# Test manually
cd ~/AgentAPI
source venv/bin/activate
python app.py
```

### Port Already in Use

```bash
# Find process using port 5000
sudo lsof -i :5000

# Kill process
sudo kill -9 <PID>
```

## Security Considerations

1. **Never commit `.env` file** - Contains sensitive credentials
2. **Use IAM roles** - Instead of hardcoding AWS credentials
3. **Enable SSL/TLS** - Use Let's Encrypt for HTTPS
4. **Restrict database access** - Use security groups and VPC
5. **Rate limiting** - Consider adding rate limiting to API
6. **Keep dependencies updated** - Regularly update packages

## Monitoring

### Check Application Status

```bash
sudo systemctl status traffic-assistant
```

### View Logs

```bash
sudo journalctl -u traffic-assistant -f
```

### Monitor Resources

```bash
htop
```

## Updating the Application

```bash
cd ~/AgentAPI
source venv/bin/activate

# Pull latest changes (if using Git)
git pull

# Install/update dependencies
pip install -r requirements.txt

# Restart service
sudo systemctl restart traffic-assistant
```

## Performance Tips

1. **Use connection pooling** - Already configured in `app.py`
2. **Add database indexes** - On frequently queried columns
3. **Cache geocoding results** - Implement Redis for coordinate caching
4. **Scale horizontally** - Add more EC2 instances behind a load balancer

## License

This project is for internal use.

## Support

For issues or questions, contact the development team.
