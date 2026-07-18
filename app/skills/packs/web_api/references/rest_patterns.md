# REST API Design Patterns — Reference Guide

## Common REST Patterns

### Resource-Oriented Routes
```
GET    /api/v1/users          → List users
GET    /api/v1/users/:id      → Get single user
POST   /api/v1/users          → Create user
PUT    /api/v1/users/:id      → Update user
DELETE /api/v1/users/:id      → Delete user
```

### Nested Resources
```
GET    /api/v1/users/:id/orders        → List user's orders
POST   /api/v1/users/:id/orders        → Create order for user
```

### Query Parameters for Filtering
```
GET /api/v1/users?status=active&role=admin&page=2&limit=20
```

## Framework-Specific Patterns

### FastAPI (Python)
```python
@app.get("/users/{user_id}")
@router.post("/users/", response_model=User)
```

### Express (Node.js)
```javascript
app.get('/users/:id', getUser)
router.post('/users', createUser)
```

### Spring MVC (Java)
```java
@GetMapping("/users/{id}")
@PostMapping(value = "/users")
@RequestMapping(method = RequestMethod.GET)
```

### Gin (Go)
```go
r.GET("/users/:id", getUser)
r.POST("/users", createUser)
```

## Auth Patterns

### JWT Token Flow
1. Client sends credentials to `/auth/login`
2. Server validates → returns signed JWT
3. Client includes `Authorization: Bearer <token>` in subsequent requests
4. Server verifies token signature on each request

### OAuth2 Flows
- **Authorization Code**: web apps (redirects to provider)
- **Client Credentials**: machine-to-machine
- **Resource Owner Password**: deprecated but still seen

### API Key Patterns
- Header: `X-API-Key: <key>`
- Query param: `?api_key=<key>`
- Custom header variations

## gRPC Patterns

### Proto Service Definition
```proto
service UserService {
  rpc GetUser (GetUserRequest) returns (User);
  rpc ListUsers (ListUsersRequest) returns (ListUsersResponse);
  rpc CreateUser (CreateUserRequest) returns (User);
}
```

## Error Handling Patterns

### Standard HTTP Error Codes in APIs
- 400: Bad Request (validation failure)
- 401: Unauthorized (missing/invalid auth)
- 403: Forbidden (insufficient permissions)
- 404: Not Found
- 409: Conflict (duplicate resource)
- 422: Unprocessable Entity
- 429: Too Many Requests (rate limited)
- 500: Internal Server Error
