#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    int id;
    int difficulty;
} Topic;

int main(int argc, char *argv[])
{
    if (argc < 4) return 1;

    int days_left = atoi(argv[1]);
    double hours_per_day = atof(argv[2]);
    char *input_data = argv[3];

    Topic topics[1000];
    int topic_count = 0;

    char *token = strtok(input_data, "|");
    while (token != NULL && topic_count < 1000)
    {
        sscanf(token, "%d,%d", &topics[topic_count].id, &topics[topic_count].difficulty);
        topic_count++;
        token = strtok(NULL, "|");
    }

    if (topic_count == 0) return 0;
    if (days_left <= 0) days_left = 1;

    int total_difficulty = 0;
    for (int i = 0; i < topic_count; i++)
    {
        total_difficulty += topics[i].difficulty;
    }

    double diff_per_day = (double)total_difficulty / days_left;

    int current_sum = 0;
    for (int i = 0; i < topic_count; i++)
    {
        if (i > 0) printf(",");
        printf("%d", topics[i].id);
        current_sum += topics[i].difficulty;

        if (current_sum >= diff_per_day)
        {
            break;
        }
    }

    return 0;
}