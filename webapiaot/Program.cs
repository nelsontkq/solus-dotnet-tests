var builder = WebApplication.CreateSlimBuilder(args);

var app = builder.Build();

app.MapGet("TEST", () => "SUCCESS");

app.Run();
