#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    char name[100];
    int difficulty;
} Topic;

int main(int argc, char *argv[])
{
    if (argc < 4)
    {
        return 1;
    }

    int days_left = atoi(argv[1]);
    double hours_per_day = atof(argv[2]);
    char *input_data = argv[3];

    Topic topics[100];
    int topic_count = 0;

    char *token = strtok(input_data, "|");
    while (token != NULL && topic_count < 100)
    {
        sscanf(token, "%[^,],%d", topics[topic_count].name, &topics[topic_count].difficulty);
        topic_count++;
        token = strtok(NULL, "|");
    }

    int total_difficulty = 0;
    for (int i = 0; i < topic_count; i++)
    {
        total_difficulty += topics[i].difficulty; // FIX: was "idfficulty" (typo)
    }

    if (days_left <= 0) days_left = 1;
    double diff_per_day = (double)total_difficulty / days_left;

    int current_sum = 0;
    for (int i = 0; i < topic_count; i++)
    {
        printf("%s", topics[i].name);
        current_sum += topics[i].difficulty;

        if (current_sum >= diff_per_day || i == topic_count - 1)
        {
            break;
        }
        printf(",");
    }

    return 0;
}
